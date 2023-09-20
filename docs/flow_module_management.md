# Flow Module Management

Flow is a sharing-oriented platform, empowering users to contribute their personal Flows, called **flow modules**, to Hugging Face. 

## Flow Modules

- Each Hugging Face published repository corresponds to a self-contained flow module. For instance, [saibo/OpenAIChatFlows](https://huggingface.co/saibo/OpenAIChatFlows) is a flow module. 
- A module may include multiple Flow classes and potentially a default configuration YAML file. In the [saibo/OpenAIChatFlows](https://huggingface.co/saibo/OpenAIChatFlows) module, you can find [OpenAIChatGPT4.py](https://huggingface.co/saibo/OpenAIChatFlows/blob/main/OpenAIChatGPT4.py).
- Each Flow class can depend on other remote, publicly available modules. For example, [OpenAIChatGPT4.py](https://huggingface.co/saibo/OpenAIChatFlows/blob/main/OpenAIChatGPT4.py) depends on [martinjosifoski/OpenAIChatAtomicFlow](https://huggingface.co/martinjosifoski/OpenAIChatAtomicFlow/tree/main).

## Syncing Flow Modules

To use or import a flow module, first sync it to the `flow_modules` directory in your root directory. You can then import it like any local Python package. Consider the following `trivial_sync_demo.py`, which relies on [saibo/OpenAIChatFlows](https://huggingface.co/saibo/OpenAIChatFlows):

```python
dependencies = [
    {"url": "saibo/OpenAIChatFlows", "revision": "main"},
]
from flows import flow_verse
flow_verse.sync_dependencies(dependencies) 

from flow_modules.saibo.OpenAIChatFlows import OpenAIChatGPT4

if __name__ == "__main__":
	print("This is a trivial sync demo.")
```

This sync process, while initially unusual, offers several benefits:
- Inspect the implementation of remote flow modules without swapping between your IDE and a webpage. Additionally, benefit from IDE features like intellisense.
- Easily build on an existing implementation without needing to download or clone the repository yourself. You can then [create a PR with ease](TODO).

## Flow Module Namespace

- Remote flow modules are identified by their Hugging Face repo ID and revision, e.g., `saibo/OpenAIChatFlows:main`.
- Each locally synced flow module is a valid Python package found under the `flow_modules` directory. **Only one revision** is kept for each remote flow module, e.g., `flow_modules.saibo.OpenAIChatFlows`. If there's a revision conflict, a warning will prompt you to choose which version to keep.

For example, your file structure might look like this:

```shell
(flows) ➜  dev-tutorial tree .
.
├── flow_modules
│   ├── martinjosifoski
│   │   └── OpenAIChatAtomicFlow
│   │       ├── FLOW_MODULE_ID
│   │       ├── OpenAIChatAtomicFlow.py
│   │       ├── OpenAIChatAtomicFlow.yaml
│   │       ├── README.md
│   │       ├── __init__.py
│   │       └── __pycache__
│   │           ├── OpenAIChatAtomicFlow.cpython-39.pyc
│   │           └── __init__.cpython-39.pyc
│   └── saibo
│       └── OpenAIChatFlows
│           ├── FLOW_MODULE_ID
│           ├── OpenAIChatGPT4.py
│           ├── OpenAIChatGPT4.yaml
│           ├── README.md
│           ├── __init__.py
│           └── __pycache__
│               ├── OpenAIChatGPT4.cpython-39.pyc
│               └── __init__.cpython-39.pyc
└── trivial_sync_demo.py

9 directories, 16 files
```

As illustrated, the flow module `saibo/OpenAIChatFlows` depends on the remote flow module `martinjosifoski/OpenAIChatAtomicFlow`. Both of these dependencies are synchronized under the `flow_modules` directory. For the `saibo/OpenAIChatFlows` module, it syncs and imports its dependencies in the same way, maintaining consistency in the sync logic across both remote and local development.

```python
dependencies = [
    {"url": "martinjosifoski/OpenAIChatAtomicFlow", "revision": "cae3fdf2f0ef7f28127cf4bc35ce985c5fc4d19a"}
]
from flows import flow_verse
flow_verse.sync_dependencies(dependencies) 

from flow_modules.martinjosifoski.OpenAIChatAtomicFlow import OpenAIChatAtomicFlow

class OpenAIChatGPT4(OpenAIChatAtomicFlow):
    def __init__(self, **kwargs):
```
The namespace for flow modules is consistent with its Hugging Face repo ID, meaning `martinjosifoski/OpenAIChatAtomicFlow` will be synced as `flow_modules.martinjosifoski.OpenAIChatAtomicFlow`.

If you wish to discard all your changes to a synced module, you can add an `overwrite` parameter to the dependencies. This will cause all of your modifications to be replaced with the original content of the specified revision:

```python
dependencies = [
    {"url": "martinjosifoski/OpenAIChatAtomicFlow", "revision": "cae3fdf2f0ef7f28127cf4bc35ce985c5fc4d19a", "overwrite": True}
]
```

Note that HuggingFace's user name and repository name can be prefixed with numbers. For example `1234/6789` is a valid repository id for HuggingFace. However, python does not allow its module name to be prefixed with numbers. `import 1234.6789` is illegal. In Flows, the repository id of the flow module has following implications:

- the user name can be prefixed with a number, as we cannot ask a user to change their name. The flow module will be synced into `./flow_modules/user_{NUMBER_PREFIX_USERNAME}`. So we add a prefix to the synced python module, such that it can be correctly imported.
- the repository name **cannot** be prefixed with a number. Repository name is easy to change. A alphabetic-prefixed name is also easier for your audience to understand.