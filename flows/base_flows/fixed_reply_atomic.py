from typing import List, Dict, Any, Optional

from flows.base_flows.abstract import AtomicFlow


# ToDo: Rename to FixedReplyFlow (and propagate the change to CC Flows & Tutorials)
class FixedReplyAtomicFlow(AtomicFlow):
    REQUIRED_KEYS_CONFIG = ["fixed_reply"]
    REQUIRED_KEYS_CONSTRUCTOR = []

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def run(self,
            input_data: Dict[str, Any],
            private_keys: Optional[List[str]] = [],
            keys_to_ignore_for_hash: Optional[List[str]] = []) -> Dict[str, Any]:

        return self.flow_config["fixed_reply"]

