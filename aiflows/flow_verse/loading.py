import os
import re
import sys
import shutil
import inspect
import filecmp
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
import threading

import colorama
import huggingface_hub
from huggingface_hub.hf_api import HfApi

from aiflows.utils import logging
import subprocess
import pkg_resources
import importlib
from aiflows.flow_verse import utils

logger = logging.get_logger(__name__)
logger.warn = logger.warning

_default_home = os.path.join(os.path.expanduser("~"), ".cache")
_flows_cache_home = os.path.expanduser(os.path.join(_default_home, "aiflows"))
DEFAULT_CACHE_PATH = os.path.join(_flows_cache_home, "flow_verse")
DEFAULT_FLOW_MODULE_FOLDER = "flow_modules"
FLOW_MODULE_SUMMARY_FILE_NAME = "flow.mod"
REVISION_FILE_HEADER = """\
########################################
# auto-generated by aiflows, DO NOT EDIT #
########################################\
"""

DEFAULT_REMOTE_REVISION = "main"
NO_COMMIT_HASH = "NO_COMMIT_HASH"

_lock = threading.Lock()


@dataclass
class FlowModuleSpec:
    """This class contains the flow module specification.

    :param repo_id: The repository ID
    :type repo_id: str
    :param revision: The revision
    :type revision: str
    :param commit_hash: The commit hash
    :type commit_hash: str
    :param cache_dir: The cache directory
    :type cache_dir: str
    :param sync_dir: The sync directory
    :type sync_dir: str
    """

    repo_id: str
    revision: str
    commit_hash: str
    cache_dir: str
    sync_dir: str

    @staticmethod
    def build_mod_id(repo_id: str, revision: str):
        """Static method that builds a module ID from a repository ID and a revision."""
        return f"{repo_id}:{revision}"

    @property
    def mod_id(self):
        """Returns the module ID."""
        return self.build_mod_id(self.repo_id, self.revision)


"""
########################################
# auto-generated by aiflows, DO NOT EDIT #
########################################
sync_root: xxxx
saibo/aaaa {revision} {commit_hash} -> _/saibo/aaaa
3Represent/bbbb {revision} {commit_hash} -> _/user_3Represent/bbbb
"""

# TODO(yeeef): huggingface username spec: Letters, numbers, dashes. No dash at the end or the start, no consecutive dashes. Not just numbers.; r"^(?!-)(?!.*-$)(?!.*--)[a-zA-Z0-9-]+(?<!^\d+)$"
#       model name spec: Only regular alphanumeric characters, '-', ' and '_' supported; r"^[a-zA-Z0-9\-_' ]+$"

# TODO(yeeef): lock to protect the singleton

"""
flow module data model

in flow.mod
keyed by repo_id, for each repo_id, we only preserve one (revision+commit_hash); we only preserve one version for each repo_id

flow_mod_id: repo_id:revision (it is still not unique, as same revision might corresponds to differernt commit hash, but it is a user-friendly format)
"""


class FlowModuleSpecSummary:
    """This class contains the flow module specification summary.

    :param sync_root: The sync root
    :type sync_root: str
    :param cache_root: The cache root
    :type cache_root: str
    :param mods: The modules
    :type mods: List[FlowModuleSpec], optional
    """

    def __init__(self, sync_root: str, cache_root: str, mods: List[FlowModuleSpec] = None) -> None:
        if mods is None:
            mods = []
        self._sync_root = sync_root
        self._cache_root = cache_root
        self._mods = {mod.repo_id: mod for mod in mods}

    @property
    def cache_root(self) -> str:
        """
        Returns the remote cache root.

        :return: The remote cache root.
        :rtype: str
        """
        return self._cache_root

    @property
    def sync_root(self) -> str:
        """
        Returns the sync root.

        :return: The sync root.
        :rtype: str
        """
        return self._sync_root

    def get_mods(self) -> List[FlowModuleSpec]:
        """
        Returns a list of `FlowModuleSpec` objects.

        :return: A list of `FlowModuleSpec` objects.
        :rtype: List[FlowModuleSpec]
        """
        return list(self._mods.values())

    def add_mod(self, flow_mod_spec: FlowModuleSpec):
        """
        Adds a FlowModuleSpec object to the FlowModuleSpecSummary object.

        :param flow_mod_spec: The FlowModuleSpec object to be added.
        :type flow_mod_spec: FlowModuleSpec
        """
        self._mods[flow_mod_spec.repo_id] = flow_mod_spec

    def get_mod(self, repo_id: str) -> Optional[FlowModuleSpec]:
        """
        Returns the `FlowModuleSpec` object for the specified repository ID.

        :param repo_id: The repository ID.
        :type repo_id: str
        :return: The `FlowModuleSpec` object for the specified repository ID, or `None` if not found.
        :rtype: Optional[FlowModuleSpec]
        """
        return self._mods.get(repo_id, None)

    @staticmethod
    def from_flow_mod_file(file_path: str) -> Optional["FlowModuleSpecSummary"]:
        """
        Reads a flow module file and returns a `FlowModuleSpecSummary` object.

        :param file_path: The path to the flow module file.
        :type file_path: str
        :return: A `FlowModuleSpecSummary` object if the file exists, otherwise `None`.
        :rtype: Optional["FlowModuleSpecSummary"]
        :raises ValueError: If the flow module file is invalid.
        """

        sync_root_pattern = re.compile(r"^sync_root: (.+)$")
        cache_root_pattern = re.compile(r"^cache_root: (.+)$")
        flow_mod_spec_pattern = re.compile(r"^(.+)/(.+) (.+) (.+) -> _/(.+)$")
        if not os.path.exists(file_path):
            return None

        with open(file_path, "r") as f:
            # read header
            for header_line in REVISION_FILE_HEADER.split("\n"):
                if header_line.strip() != f.readline().strip():
                    raise ValueError(f"Invalid flow module file {file_path}, header is corrupted")

            sync_root_line = f.readline().strip()
            sync_root_match = re.search(sync_root_pattern, sync_root_line)
            if not sync_root_match:
                raise ValueError(f"Invalid flow module file {file_path}, the first line must be `sync_root: xxxx`")
            sync_root = sync_root_match.group(1)

            cache_root_line = f.readline().strip()
            cache_root_match = re.search(cache_root_pattern, cache_root_line)
            if not cache_root_match:
                raise ValueError(f"Invalid flow module file {file_path}, the second line must be `cache_root: xxxx`")
            cache_root = cache_root_match.group(1)

            mods = []
            mod_line = f.readline().strip()
            while mod_line:
                flow_mod_spec_match = re.search(flow_mod_spec_pattern, mod_line)
                if not flow_mod_spec_match:
                    raise ValueError(
                        f"Invalid flow module file {file_path}, line '{mod_line}' is not a valid flow module spec"
                    )

                username, repo_name, revision, commit_hash, relative_sync_dir = flow_mod_spec_match.groups()
                repo_id = f"{username}/{repo_name}"
                sync_dir = os.path.join(sync_root, relative_sync_dir)

                if not is_local_revision(revision):  # remote revision
                    cache_dir = utils.build_hf_cache_path(repo_id, commit_hash, cache_root)
                else:
                    cache_dir = sync_dir

                flow_mod_spec = FlowModuleSpec(repo_id, revision, commit_hash, cache_dir, sync_dir)
                mods.append(flow_mod_spec)
                mod_line = f.readline().strip()

            return FlowModuleSpecSummary(sync_root, cache_root, mods)

    def serialize(self) -> str:
        """Serializes the FlowModuleSpecSummary object.

        :return: The serialized FlowModuleSpecSummary object.
        :rtype: str
        """
        lines = []
        lines.append(f"sync_root: {self._sync_root}")
        lines.append(f"cache_root: {self._cache_root}")

        for mod in self._mods.values():
            lines.append(
                f"{mod.repo_id} {mod.revision} {mod.commit_hash} -> _/{os.path.relpath(mod.sync_dir, self._sync_root)}"
            )

        return "\n".join(lines)

    def __repr__(self) -> str:
        return f"~~~ FlowModuleSpecSummary ~~~\n{self.serialize()}"

    def __str__(self) -> str:
        return self.__repr__()


def add_to_sys_path(path):
    """Adds a path to sys.path if it's not already there.

    :param path: The path to add
    :type path: str
    """
    # Make sure the path is absolute
    absolute_path = os.path.abspath(path)

    # Check if the path is in sys.path
    if absolute_path not in sys.path:
        # If it's not, add it
        sys.path.append(absolute_path)


# TODO(yeeef): add a check to make sure the module name is valid
def _is_valid_python_module_name(name):
    """Returns True if the given name is a valid python module name, False otherwise.

    :param name: The name to check
    :type name: str
    :return: True if the given name is a valid python module name, False otherwise
    """
    return re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", name) is not None


def is_local_revision(legal_revision: str) -> bool:
    """
    Check if a given revision is a local revision.

    :param legal_revision: A string representing the revision to check.
    :type legal_revision: str
    :return: True if the revision is a local revision, False otherwise.
    :rtype: bool
    """
    return os.path.exists(legal_revision)


# TODO(Yeeef): caller_module_name is shared at several places, so we should refactor the sync process into
# a class.
def validate_and_augment_dependency(dependency: Dict[str, str], caller_module_name: str) -> bool:
    """
    Validates and augments a dependency dictionary.

    :param dependency: A dictionary containing information about the dependency.
    :type dependency: Dict[str, str]
    :param caller_module_name: The name of the calling module.
    :type caller_module_name: str
    :return: True if the dependency is local, False otherwise.
    :rtype: bool
    """

    if "url" not in dependency:  # TODO(yeeef): url is not descriptive
        raise ValueError("dependency must have a `url` field")

    match = re.search(r"^(\w+)/(\w+)$", dependency["url"])
    if not match:
        raise ValueError("dependency url must be in the format of `username/repo_name`(huggingface repo)")
    username, repo_name = match.group(1), match.group(2)

    if re.search(r"^\d+\w+$", repo_name):  # repo_name is prefixed with a number
        raise ValueError(
            f"url's repo name `{repo_name}` is prefixed with a number, which is illegal in Flows, please adjust your repo name"
        )

    if re.search(r"^\d+\w+$", username):  # username is prefixed with a number

        logger.warning(
            f"[{caller_module_name}] url's username `{username}` is prefixed with a number, which is not a valid python module name, the module will be synced to ./flow_modules/user_{username}.{repo_name}, please import it as `import flow_modules.user_{username}.{repo_name}`"
        )
        username = f"user_{username}"

    dependency["mod_name"] = f"{username}/{repo_name}"

    # revision sanity check
    revision = dependency.get("revision", DEFAULT_REMOTE_REVISION)
    dep_is_local = False

    if not os.path.exists(revision):  # remote revision
        match = re.search(r"\W", revision)  # ToDo (Martin): This often fails with a cryptic error message
        if match is not None:
            raise ValueError(
                f"{revision} is identified as remote, as it does not exist locally. But it not a valid remote revision, it contains illegal characters: {match.group(0)}"
            )

    elif not os.path.isdir(revision):  # illegal local revision
        raise ValueError(f"local revision {revision} is not a valid directory")
    elif DEFAULT_FLOW_MODULE_FOLDER in revision:  # illgal local revision
        raise ValueError(f"syncing a local revision from {DEFAULT_FLOW_MODULE_FOLDER} is not recommended")
    else:  # local revision
        dep_is_local = True
        revision = os.path.abspath(revision)

    dependency["revision"] = revision

    return dep_is_local


def write_or_append_gitignore(sync_dir: str, mode: str, content: str):
    """Writes or appends a .gitignore file to the given directory.

    :param sync_dir: The directory to write the .gitignore file to
    :type sync_dir: str
    :param mode: The mode to open the file with
    :type mode: str
    :param content: The content to write to the file
    :type content: str
    """
    gitignore_path = os.path.join(sync_dir, ".gitignore")

    if os.path.exists(gitignore_path):
        with open(gitignore_path, "r") as gitignore_f:
            if content in gitignore_f.read():
                return

    with open(gitignore_path, mode) as gitignore_f:
        lines = ["\n\n\n# auto-generated by aiflows, all synced modules will be ignored by default\n", f"{content}\n"]
        gitignore_f.writelines(lines)


def create_init_py(base_dir: str):
    """Creates an __init__.py file in the given directory.

    :param base_dir: The directory to create the __init__.py file in
    :type base_dir: str
    """
    init_py_path = os.path.join(base_dir, "__init__.py")
    if not os.path.exists(init_py_path):
        with open(init_py_path, "w") as init_py_f:
            init_py_f.write("")


def remove_dir_or_link(sync_dir: str):
    """Removes a directory or a link.

    :param sync_dir: The directory or link to remove
    """
    if os.path.islink(sync_dir):
        os.remove(sync_dir)
    elif os.path.isdir(sync_dir):  # it need to be decided after islink, because isdir is also True for link
        shutil.rmtree(sync_dir)
    else:
        raise ValueError(f"Invalid sync_dir: {sync_dir}, it is not a valid directory nor a valid link")


def get_unsatisfied_pip_requirements(requirements_file):
    """ Returns a list of unsatisfied pip requirements from a requirements file.
    
    :param requirements_file: The path to the requirements file
    :type requirements_file: str
    :return: A list of unsatisfied pip requirements
    :rtype: List[str]
    """
    #reload pkg_resources to check for newly installed packages (e.g. from previous flow modules of the same flow)
    importlib.reload(pkg_resources)
    
    # Parse the requirements file
    with open(requirements_file, 'r') as f:
        requirements = [line.strip() for line in f]

    # Get the distributions of installed packages
    installed_distributions = {dist.project_name.lower(): dist for dist in pkg_resources.working_set}

    # Check if each requirement is satisfied
    unsatisfied_requirements = []
    for line in requirements:
        
        req = line.split('#')[0].strip()
        if req == '':
            continue
        req_dist = pkg_resources.Requirement.parse(req)
        installed_dist = installed_distributions.get(req_dist.project_name.lower())

        if not installed_dist or not installed_dist in req_dist:
            unsatisfied_requirements.append(req)
            
    return unsatisfied_requirements


def display_and_confirm_requirements(flow_name,requirements):
    """ Displays the uninstalled requirements for a flow and asks the user if they want to install them.
    
    :param flow_name: The name of the flow
    :type flow_name: str
    :param requirements: The list of unsatisfied pip requirements
    :type requirements: List[str]
    :return: True if the user wants to install the requirements, False otherwise
    :rtype: bool
    """
    
    if len(requirements) == 0:
        return False
    
    requirements_str = "\n".join([f"  - {req}" for req in requirements])
    
    question_message = \
        f"""\n{flow_name} is requesting to install the following pip requirements:\n{requirements_str}\n Do you want to proceed with the installation?"""
    
    no_message = \
        f"""Installation of requirements for {flow_name} is canceled. This may impact the proper functioning of the Flow."""
    
    yes_message = \
         f"Requirements from {flow_name} will be installed."
    
      
    answer = utils.yes_no_question(logger,question_message,yes_message,no_message,colorama_style=colorama.Fore.RED)
    
    return answer


def install_requirements(synced_flow_mod_spec):
    """ Installs the pip requirements (if not already installed) for a flow module.
    
    :param synced_flow_mod_spec: The synced flow module specification
    :type synced_flow_mod_spec: FlowModuleSpec
    """
    repo_id = synced_flow_mod_spec.repo_id
    requirements_file = os.path.join(synced_flow_mod_spec.sync_dir, "pip_requirements.txt")
    
    # For the moment, we require that every flow module has a pip_requirements.txt file. Should we change this?
    if not os.path.exists(requirements_file):
        raise ValueError(f"Every flow module must have a pip_requirements.txt file, but {requirements_file} does not exist for {repo_id}")
    
    # Get the unsatisfied pip requirements
    unsatisfied_requirements = get_unsatisfied_pip_requirements(requirements_file)
    
    #answer of the user on whether to install the requirements
    user_wants_to_install_requirements = display_and_confirm_requirements(repo_id,unsatisfied_requirements)
    
    #install the requirements
    if user_wants_to_install_requirements:
        subprocess.run(['pip', 'install', '-r', requirements_file])



# # TODO(Yeeef): add repo_hash and modified_flag to decrease computing


def fetch_remote(repo_id: str, revision: str, sync_dir: str, cache_root: str) -> FlowModuleSpec:
    """Fetches a remote dependency.

    :param repo_id: The repository ID
    :type repo_id: str
    :param revision: The revision
    :type revision: str
    :param sync_dir: The sync directory
    :type sync_dir: str
    :param cache_root: The cache root
    :type cache_root: str
    :return: The flow module specification
    :rtype: FlowModuleSpec
    """
    sync_dir = os.path.abspath(sync_dir)
    if is_local_sync_dir_valid(sync_dir):
        remove_dir_or_link(sync_dir)

    os.makedirs(os.path.dirname(sync_dir), exist_ok=True)
    create_init_py(os.path.dirname(sync_dir))

    # this call is only used to download the repo to cache and get cache path
    cache_mod_dir = huggingface_hub.snapshot_download(repo_id, cache_dir=cache_root, revision=revision)

    # this call will fetch the cached snapshot to the sync_dir
    huggingface_hub.snapshot_download(repo_id, cache_dir=cache_root, local_dir=sync_dir, revision=revision)

    commit_hash = extract_commit_hash_from_cache_mod_dir(cache_mod_dir)

    flow_mod_spec = FlowModuleSpec(repo_id, revision, commit_hash, cache_mod_dir, sync_dir)

    return flow_mod_spec


def fetch_local(repo_id: str, file_path: str, sync_dir: str) -> FlowModuleSpec:
    """Fetches a local dependency.

    :param repo_id: The repository ID
    :type repo_id: str
    :param file_path: The file path
    :type file_path: str
    :param sync_dir: The sync directory
    :type sync_dir: str
    :return: The flow module specification
    :rtype: FlowModuleSpec
    """
    # shutil.copytree(file_path, sync_dir, ignore=shutil.ignore_patterns(".git"), dirs_exist_ok=overwrite)
    sync_dir = os.path.abspath(sync_dir)
    # when fetch_local is triggered, the old dir is always going to be removed
    if is_local_sync_dir_valid(sync_dir):
        remove_dir_or_link(sync_dir)

    os.makedirs(os.path.dirname(sync_dir), exist_ok=True)
    os.symlink(file_path, sync_dir)

    flow_mod_spec = FlowModuleSpec(repo_id, file_path, NO_COMMIT_HASH, file_path, sync_dir)

    return flow_mod_spec


def is_local_sync_dir_valid(sync_dir: str):
    """Returns True if the sync_dir is a valid local sync dir, False otherwise.

    :param sync_dir: The sync directory
    :type sync_dir: str
    """
    return os.path.isdir(sync_dir) or os.path.islink(sync_dir)


def retrive_commit_hash_from_remote(repo_id: str, revision: str) -> str:
    """Retrieves the commit hash from a remote repository.

    :param repo_id: The repository ID
    :type repo_id: str
    :param revision: The revision
    :type revision: str
    :return: The commit hash
    :rtype: str
    """
    hf_api = HfApi()
    repo_info = hf_api.repo_info(repo_id=repo_id, repo_type="model", revision=revision, token=None)
    commit_hash = repo_info.sha
    return commit_hash


def extract_commit_hash_from_cache_mod_dir(cache_mod_dir: str) -> str:
    """Extracts the commit hash from a cache directory.

    :param cache_mod_dir: The cache directory
    :type cache_mod_dir: str
    :return: The commit hash
    :rtype: str
    """
    return os.path.basename(cache_mod_dir)


def is_sync_dir_modified(sync_dir: str, cache_dir: str) -> bool:
    """Returns True if the sync_dir is modified compared to the cache_dir, False otherwise.

    :param sync_dir: The sync directory
    :type sync_dir: str
    :cache_dir: The cache directory
    :type cache_dir: str
    :return: True if the sync_dir is modified compared to the cache_dir, False otherwise
    :rtype: bool
    """
    with os.scandir(cache_dir) as it:
        for entry in it:
            # TODO(Yeeef): remove `entry.name.startswith('.')`
            if entry.name.startswith(".") or entry.name == "__pycache__":
                continue

            if entry.is_file():
                same = filecmp.cmp(
                    os.path.join(cache_dir, entry.name), os.path.join(sync_dir, entry.name), shallow=False
                )
                if not same:
                    logger.debug(
                        f"File {os.path.join(cache_dir, entry.name)} is not the same as {os.path.join(sync_dir, entry.name)}"
                    )
                    return True
            elif entry.is_dir():
                dir_same = is_sync_dir_modified(os.path.join(sync_dir, entry.name), os.path.join(cache_dir, entry.name))
                if not dir_same:
                    return True
            else:
                raise ValueError(
                    f"Invalid file: {os.path.join(cache_dir, entry.name)}, it is not file or dir or valid symlink"
                )

    return False


def sync_remote_dep(
    previous_synced_flow_mod_spec: Optional[FlowModuleSpec],
    repo_id: str,
    mod_name: str,
    revision: str,
    caller_module_name: str,
    sync_root: str,
    cache_root: str = DEFAULT_CACHE_PATH,
    overwrite: bool = False,
) -> FlowModuleSpec:
    """
    Synchronizes a remote dependency.

    :param previous_synced_flow_mod_spec: The previously synced flow module specification.
    :type previous_synced_flow_mod_spec: Optional[FlowModuleSpec]
    :param repo_id: The ID of the repository.
    :type repo_id: str
    :param mod_name: The name of the module.
    :type mod_name: str
    :param revision: The revision of the module.
    :type revision: str
    :param caller_module_name: The name of the caller module.
    :type caller_module_name: str
    :param cache_root: The root directory of the cache. Defaults to DEFAULT_CACHE_PATH.
    :type cache_root: str
    :param overwrite: Whether to overwrite the existing module or not. Defaults to False.
    :type overwrite: bool
    :return: The synced flow module specification.
    :rtype: FlowModuleSpec
    """
    synced_flow_mod_spec = None
    flow_mod_id = FlowModuleSpec.build_mod_id(repo_id, revision)
    sync_dir = os.path.abspath(os.path.join(sync_root, mod_name))

    if previous_synced_flow_mod_spec is None:  # directly sync without any warning
        logger.info(f"{flow_mod_id} will be fetched from remote")
        synced_flow_mod_spec = fetch_remote(repo_id, revision, sync_dir, cache_root)
        return synced_flow_mod_spec

    ### we have a previously synced flow mod spec which has same **repo_id**
    assert sync_dir == previous_synced_flow_mod_spec.sync_dir, (sync_dir, previous_synced_flow_mod_spec.sync_dir)

    # update if (revision, commit_hash) changed
    remote_revision_commit_hash_changed = False
    remote_commit_hash = retrive_commit_hash_from_remote(repo_id, revision)
    remote_revision_commit_hash_changed = remote_commit_hash != previous_synced_flow_mod_spec.commit_hash

    # check if the file is modified compared to the cache_dir
    sync_dir_modified = is_sync_dir_modified(sync_dir, previous_synced_flow_mod_spec.cache_dir)

    if overwrite:
        
        question_message = \
            f"[{caller_module_name}] {flow_mod_id} will be overwritten, are you sure?"
        
        no_message = \
            f"[{caller_module_name}] {flow_mod_id} will not be overwritten."
            
        yes_message = \
            f"[{caller_module_name}]{flow_mod_id} will be fetched from remote."
        
        overwrite = utils.yes_no_question(logger, question_message,yes_message,no_message)
        
        if not overwrite:
            synced_flow_mod_spec = previous_synced_flow_mod_spec
        else:
            synced_flow_mod_spec = fetch_remote(repo_id, revision, sync_dir, cache_root)

    elif previous_synced_flow_mod_spec.mod_id != flow_mod_id:
        # user has supplied a new flow_mod_id, we fetch the remote directly with warning
        
        question_message =  \
            """{previous_synced_flow_mod_spec.mod_id} already synced, it will be overwritten by new revision {flow_mod_id}, are you sure? """
        
        no_message = \
            f"[{caller_module_name}] {previous_synced_flow_mod_spec.mod_id} will not be overwritten."
        
        yes_message = \
            f"[{caller_module_name}] {previous_synced_flow_mod_spec.mod_id} will be fetched from remote."
        
        fetch_from_remote = utils.yes_no_question(logger, question_message,yes_message,no_message)   
        
        if not fetch_from_remote:
            synced_flow_mod_spec = previous_synced_flow_mod_spec
        else:
            synced_flow_mod_spec = fetch_remote(repo_id, revision, sync_dir, cache_root)
            
    ### user has supplied same flow_mod_id(repo_id:revision), we check if the remote commit has changed
    elif not remote_revision_commit_hash_changed:
        # trivial case, we do nothing
        logger.info(f"{flow_mod_id} already synced, skip")
        synced_flow_mod_spec = previous_synced_flow_mod_spec
    elif not sync_dir_modified:
        # remote has changed but local is not modified, we fetch the remote with a warning
        logger.warn(
            f"{colorama.Fore.RED}[{caller_module_name}] {previous_synced_flow_mod_spec.mod_id}'s commit hash has changed from {previous_synced_flow_mod_spec.commit_hash} to {remote_commit_hash}, as synced module is not modified, the newest commit regarding {previous_synced_flow_mod_spec.mod_id} will be fetched{colorama.Style.RESET_ALL}"
        )
        synced_flow_mod_spec = fetch_remote(repo_id, revision, sync_dir, cache_root)
    else:
        # synced dir is modified and remote has changed, we do nothing with a warning
        logger.warn(
            f"{colorama.Fore.RED}[{caller_module_name}] {previous_synced_flow_mod_spec.mod_id}'s commit hash has changed from {previous_synced_flow_mod_spec.commit_hash} to {remote_commit_hash}, but synced module is already modified, the newest commit regarding {previous_synced_flow_mod_spec.mod_id} will NOT be fetched{colorama.Style.RESET_ALL}"
        )
        synced_flow_mod_spec = previous_synced_flow_mod_spec

    return synced_flow_mod_spec


def sync_local_dep(
    previous_synced_flow_mod_spec: Optional[FlowModuleSpec],
    repo_id: str,
    mod_name: str,
    revision: str,
    caller_module_name: str,
    sync_root: str,
    overwrite: bool = False,
) -> FlowModuleSpec:
    """
    Synchronize a local dependency.

    :param previous_synced_flow_mod_spec: The previously synced flow module specification.
    :type previous_synced_flow_mod_spec: Optional[FlowModuleSpec]
    :param repo_id: The ID of the repository.
    :type repo_id: str
    :param mod_name: The name of the module.
    :type mod_name: str
    :param revision: The revision of the module.
    :type revision: str
    :param caller_module_name: The name of the caller module.
    :type caller_module_name: str
    :param overwrite: Whether to overwrite the previously synced flow module specification. Defaults to False.
    :type overwrite: bool
    :return: The synced flow module specification.
    :rtype: FlowModuleSpec
    """

    synced_flow_mod_spec = None
    flow_mod_id = FlowModuleSpec.build_mod_id(repo_id, revision)
    module_synced_from_dir = revision
    sync_dir = os.path.abspath(os.path.join(sync_root, mod_name))

    if not os.path.isdir(module_synced_from_dir):
        raise ValueError(
            f"local dependency {flow_mod_id}'s revision {module_synced_from_dir} is not a valid local directory"
        )

    if previous_synced_flow_mod_spec is None:  # directly sync without any warning
        logger.info(f"{flow_mod_id} will be fetched from local")
        synced_flow_mod_spec = fetch_local(repo_id, revision, sync_dir)
        return synced_flow_mod_spec

    ### we have a previously synced flow mod spec which has same **repo_id**
    assert sync_dir == previous_synced_flow_mod_spec.sync_dir, (sync_dir, previous_synced_flow_mod_spec.sync_dir)

    if overwrite:
        
        question_message = \
            f"[{caller_module_name}] {flow_mod_id} will be overwritten, are you sure?"
            
        no_message = \
            f"[{caller_module_name}] {flow_mod_id} will not be overwritten."
            
        yes_message = \
            f"[{caller_module_name}] {flow_mod_id} will be fetched from local."
            
        overwrite = utils.yes_no_question(logger, question_message,yes_message,no_message)
        
        if not overwrite:
            synced_flow_mod_spec = previous_synced_flow_mod_spec
        else:
            synced_flow_mod_spec = fetch_local(repo_id, module_synced_from_dir, sync_dir)

    elif previous_synced_flow_mod_spec.mod_id != flow_mod_id:
        
        question_message = \
            f"[{caller_module_name}] {previous_synced_flow_mod_spec.mod_id} already synced, it will be overwritten by {flow_mod_id}, are you sure?"

        no_message = \
            f"[{caller_module_name}] {previous_synced_flow_mod_spec.mod_id} will not be overwritten."
        
        yes_message = \
            f"[{caller_module_name}] {previous_synced_flow_mod_spec.mod_id} will be fetched from local."
            
        fetch_from_local = utils.yes_no_question(logger, question_message,yes_message,no_message)
        
        if not fetch_from_local:
            synced_flow_mod_spec = previous_synced_flow_mod_spec
        else:
            synced_flow_mod_spec = fetch_local(repo_id, module_synced_from_dir, sync_dir)
            
    else:
        logger.info(f"{flow_mod_id} already synced, skip")
        synced_flow_mod_spec = previous_synced_flow_mod_spec

    return synced_flow_mod_spec


def create_empty_flow_mod_file(sync_root: str, cache_root: str, overwrite: bool = False) -> str:
    """
    Creates an empty flow module file.

    :param sync_root: The sync root
    :type sync_root: str
    :param cache_root: The cache root
    :type cache_root: str
    :param overwrite: Whether to overwrite the existing flow module file. Defaults to False.
    :type overwrite: bool
    :return: The path to the flow module file.
    :rtype: str
    """
    flow_mod_summary_path = os.path.join(sync_root, FLOW_MODULE_SUMMARY_FILE_NAME)
    if os.path.exists(flow_mod_summary_path) and not overwrite:
        return flow_mod_summary_path

    with open(flow_mod_summary_path, "w") as f:
        lines = [REVISION_FILE_HEADER, f"sync_root: {sync_root}", f"cache_root: {cache_root}"]
        f.write("\n".join(lines) + "\n")

    write_or_append_gitignore(sync_root, "w", content="*")

    return flow_mod_summary_path


def write_flow_mod_summary(flow_mod_summary_path: str, flow_mod_summary: FlowModuleSpecSummary):
    """Writes a flow module summary to a file.

    :param flow_mod_summary_path: The path to the flow module summary file.
    :type flow_mod_summary_path: str
    :param flow_mod_summary: The flow module summary.
    :type flow_mod_summary: FlowModuleSpecSummary
    """
    with open(flow_mod_summary_path, "w") as f:
        f.write(REVISION_FILE_HEADER)
        f.write("\n")
        f.write(flow_mod_summary.serialize())
        f.write("\n")


def _sync_dependencies(
    dependencies: List[Dict[str, str]],
    all_overwrite: bool,
    flow_modules_base_dir: str,
    cache_root: str,
    caller_module_name: str,
) -> FlowModuleSpecSummary:
    """Synchronizes dependencies.

    :param dependencies: The dependencies to synchronize
    :type dependencies: List[Dict[str, str]]
    :param all_overwrite: Whether to overwrite all existing modules or not
    :type all_overwrite: bool
    :param flow_modules_base_dir: The base directory of the flow modules
    :type flow_modules_base_dir: str
    :param cache_root: The cache root
    :type cache_root: str
    :param caller_module_name: The name of the caller module
    :type caller_module_name: str
    :return: The flow module specification summary
    :rtype: FlowModuleSpecSummary
    """
    with _lock:
        add_to_sys_path(flow_modules_base_dir)
        add_to_sys_path(os.path.join(flow_modules_base_dir, DEFAULT_FLOW_MODULE_FOLDER))

        sync_root = os.path.abspath(os.path.join(flow_modules_base_dir, DEFAULT_FLOW_MODULE_FOLDER))
        logger.info(
            f"{colorama.Fore.GREEN}[{caller_module_name}]{colorama.Style.RESET_ALL} started to sync flow module dependencies to {sync_root}..."
        )

        if not os.path.exists(sync_root):
            os.mkdir(sync_root)
            create_init_py(sync_root)
        elif not os.path.isdir(sync_root):
            raise ValueError(f"flow module folder {sync_root} is not a directory")

        flow_mod_summary_path = create_empty_flow_mod_file(sync_root, cache_root)
        flow_mod_summary = FlowModuleSpecSummary.from_flow_mod_file(flow_mod_summary_path)
        # logger.debug(f"flow mod summary: {flow_mod_summary}")

        for dep in dependencies:
            dep_is_local = validate_and_augment_dependency(dep, caller_module_name)
            dep_overwrite = dep.get("overwrite", False)
            url, revision, mod_name = dep["url"], dep["revision"], dep["mod_name"]

            synced_flow_mod_spec = None
            previous_synced_flow_mod_spec = flow_mod_summary.get_mod(url)
            if dep_is_local:
                synced_flow_mod_spec = sync_local_dep(
                    previous_synced_flow_mod_spec,
                    url,
                    mod_name,
                    revision,
                    caller_module_name,
                    sync_root,
                    all_overwrite or dep_overwrite,
                )
                # logger.debug(f"add local dep {synced_flow_mod_spec} to flow_mod_summary")
            else:
                synced_flow_mod_spec = sync_remote_dep(
                    previous_synced_flow_mod_spec,
                    url,
                    mod_name,
                    revision,
                    caller_module_name,
                    sync_root,
                    cache_root,
                    all_overwrite or dep_overwrite,
                )
                # logger.debug(f"add remote dep {synced_flow_mod_spec} to flow_mod_summary")
            flow_mod_summary.add_mod(synced_flow_mod_spec)
            install_requirements(synced_flow_mod_spec)

        # write flow.mod
        # logger.debug(f"write flow mod summary: {flow_mod_summary}")
        write_flow_mod_summary(flow_mod_summary_path, flow_mod_summary)

        logger.info(f"{colorama.Fore.GREEN}[{caller_module_name}]{colorama.Style.RESET_ALL} finished syncing\n\n")
        return flow_mod_summary


def sync_dependencies(dependencies: List[Dict[str, str]], all_overwrite: bool = False) -> List[str]:
    """Synchronizes dependencies. (uses the _sync_dependencies function)

    :param dependencies: The dependencies to synchronize
    :type dependencies: List[Dict[str, str]]
    :param all_overwrite: Whether to overwrite all existing modules or not
    :type all_overwrite: bool
    :return: A list of sync directories
    :rtype: List[str]
    """
    caller_frame = inspect.currentframe().f_back
    caller_module = inspect.getmodule(caller_frame)
    if caller_module is None:  # https://github.com/epfl-dlab/flows/issues/50
        caller_module_name = "<interactive>"
    else:
        caller_module_name = caller_module.__name__

    flow_mod_summary = _sync_dependencies(
        dependencies, all_overwrite, os.curdir, DEFAULT_CACHE_PATH, caller_module_name
    )

    return [mod.sync_dir for mod in flow_mod_summary.get_mods()]
