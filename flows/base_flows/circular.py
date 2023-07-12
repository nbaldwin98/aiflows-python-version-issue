from typing import List, Dict, Any, Optional

from flows.base_flows import CompositeFlow
from flows.utils.general_helpers import validate_parameters
from ..utils import logging

log = logging.get_logger(__name__)



class CircularFlow(CompositeFlow):
    REQUIRED_KEYS_CONFIG = ["max_rounds", "reset_every_round", "early_exit_key"]
    REQUIRED_KEYS_CONSTRUCTOR = ["subflows"]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    @classmethod
    def _validate_parameters(cls, kwargs):
        validate_parameters(cls, kwargs)

        assert len(kwargs["subflows"]) > 0, f"Circular flow needs at least one flow, currently has 0"

    def run(self,
            input_data: Dict[str, Any],
            private_keys: Optional[List[str]] = [],
            keys_to_ignore_for_hash: Optional[List[str]] = []) -> Dict[str, Any]:
        # ~~~ sets the input_data in the flow_state dict ~~~
        self._state_update_dict(update_data=input_data)

        max_round = self.flow_config.get("max_rounds", 1)
        for idx in range(max_round):
            # ~~~ Reset the generator flow if needed ~~~
            for flow_name, current_flow in self.subflows.items():
                if self.flow_config["reset_every_round"].get(flow_name, False):
                    current_flow.reset(full_reset=True, recursive=True, src_flow=self)

                output_message = self._call_flow_from_state(
                    flow_to_call=current_flow, private_keys=private_keys, keys_to_ignore_for_hash=keys_to_ignore_for_hash
                )
                self._state_update_dict(update_data=output_message)

                # ~~~ Check for end of interaction
                if self._early_exit():
                    log.info(f"[{self.flow_config['name']}] End of interaction detected")
                    break

        # ~~~ The final answer should be in self.flow_state, thus allow_class_attributes=False ~~~
        outputs = self._fetch_state_attributes_by_keys(keys=output_message.data["output_keys"],
                                                       allow_class_attributes=False)

        return outputs

    @classmethod
    def type(cls):
        return "circular"


