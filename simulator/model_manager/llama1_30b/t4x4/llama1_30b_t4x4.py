# 2024.04.11 Yixuan Mei

import os

from typing import Dict

from simulator.model_manager.base_classes import ModelOnMachine
from simulator.model_manager.llama1_30b.helper import llama30b_workload_ratio, llama30b_typical_statistics
from simulator.event_simulator.model import MachineProfile
from simulator.event_simulator.compute_node import InferenceSettings
from simulator.event_simulator.utils import load_profile_csv
from simulator.event_simulator.utils import VLLM_BLOCK_SIZE, MAX_INPUT_LEN, DECODE_PER_TOKEN_MAX_CONTEXT


class LLaMa30BonT4x4(ModelOnMachine):
    def __init__(self, num_machines_dict: Dict[str, int], typical_layers_dict: Dict[str, int],
                 normalized_perf_dict: Dict[str, float]):
        """
        LLaMa1-30B + T4 16GB x 4
        """
        # --------------- Machine Dependent Data --------------- #
        # STEP 1/3: create prompt_bs2time.csv and decode_bs2time.csv
        # STEP 2/3: some basic parameters
        machine_name: str = "T4x4"
        max_num_layers: int = 30  # use 30.8GB for parameters
        # STEP 3/3: inference settings
        vllm_num_blocks_dict: Dict[int, int] = {
            1: 123328, 2: 60196, 3: 39284, 4: 28828, 5: 22554, 6: 18372, 7: 15384, 8: 13144, 9: 11401, 10: 10007,
            11: 8866, 12: 7915, 13: 7111, 14: 6422, 15: 5824, 16: 5301, 17: 4840, 18: 4430, 19: 4063, 20: 3733,
            21: 3434, 22: 3163, 23: 2915, 24: 2687, 25: 2477, 26: 2284, 27: 2106, 28: 1940, 29: 1785, 30: 1641
        }  # num layers -> num_blocks
        prompt_max_requests_dict: Dict[int, int] = {
            1: 1, 2: 1, 3: 1, 4: 1, 5: 1, 6: 1, 7: 1, 8: 1, 9: 1, 10: 1,
            11: 1, 12: 1, 13: 1, 14: 1, 15: 1, 16: 1, 17: 1, 18: 1, 19: 1, 20: 1,
            21: 1, 22: 1, 23: 1, 24: 1, 25: 1, 26: 1, 27: 1, 28: 1, 29: 1, 30: 1
        }
        decode_max_tokens_dict: Dict[int, int] = {
            1: 180, 2: 180, 3: 180, 4: 180, 5: 180, 6: 180, 7: 180, 8: 180, 9: 180, 10: 180,
            11: 160, 12: 140, 13: 120, 14: 110, 15: 100, 16: 90, 17: 80, 18: 75, 19: 70, 20: 60,
            21: 60, 22: 50, 23: 50, 24: 45, 25: 45, 26: 40, 27: 35, 28: 35, 29: 30, 30: 25
        }
        # ------------------------------------------------------ #

        # save num machines dict
        self.machine_name: str = machine_name
        self.num_machines_dict: Dict[str, int] = num_machines_dict

        # load profile results
        dir_path = os.path.dirname(os.path.realpath(__file__))
        self.prompt_bs2time: Dict[int, float] = load_profile_csv(
            file_name=os.path.join(dir_path, "prompt_bs2time.csv")
        )
        self.prompt_bs2vram: Dict[int, float] = {
            bs: 0 for bs in self.prompt_bs2time
        }  # We set all values to 0, as vLLM has already considered this in #blocks.
        self.decode_bs2time: Dict[int, float] = load_profile_csv(
            file_name=os.path.join(dir_path, "decode_bs2time.csv")
        )
        self.decode_bs2vram: Dict[int, float] = {
            bs: 0 for bs in self.decode_bs2time
        }  # We set all values to 0, as vLLM has already considered this in #blocks.

        # kv cache & activation backup cache
        # kv_entry = vllm_num_block * block_size * num_layers
        self.max_num_layers: int = max_num_layers
        self.kv_cache_capacity: Dict[int, int] = {
            _num_layers: VLLM_BLOCK_SIZE * _num_blocks * _num_layers for _num_layers, _num_blocks in
            vllm_num_blocks_dict.items()
        }
        self.activation_backup_capacity: Dict[int, int] = {
            _num_layers: 0 for _num_layers in self.kv_cache_capacity
        }  # We set all values to 0, as we do not consider activation backup for the moment

        # build the inference settings
        self.num_layers_to_inference_settings: Dict[int, InferenceSettings] = {}
        for cur_num_layers in range(1, self.max_num_layers + 1):
            cur_workload_ratio = llama30b_workload_ratio(
                target_machine_name=machine_name,
                target_num_layers=cur_num_layers,
                num_machines_dict=num_machines_dict,
                typical_layers_dict=typical_layers_dict,
                normalized_perf_dict=normalized_perf_dict
            )
            prompt_typical_requests, prompt_typical_tokens, decode_typical_tokens = llama30b_typical_statistics(
                workload_ratio=cur_workload_ratio,
                num_kv_cache_entries=self.kv_cache_capacity[cur_num_layers],
                num_layers_on_node=cur_num_layers
            )
            assert prompt_typical_requests <= 1, "Typical requests should be less than 1!"
            self.num_layers_to_inference_settings[cur_num_layers] = InferenceSettings(
                prompt_max_requests=prompt_max_requests_dict[cur_num_layers],
                prompt_max_tokens=prompt_max_requests_dict[cur_num_layers] * MAX_INPUT_LEN,
                prompt_typical_requests=prompt_typical_requests,
                prompt_typical_tokens=prompt_typical_tokens,
                decode_max_context=decode_max_tokens_dict[cur_num_layers] * DECODE_PER_TOKEN_MAX_CONTEXT,
                decode_max_tokens=decode_max_tokens_dict[cur_num_layers],
                decode_typical_tokens=decode_typical_tokens
            )

    def get_profiling_results(self) -> MachineProfile:
        """
        Get the profiling results of running one layer of the model on the machine.

        :return: MachineProfile
        """
        machine_profile = MachineProfile(prompt_bs2time=self.prompt_bs2time, prompt_bs2vram=self.prompt_bs2vram,
                                         decode_bs2time=self.decode_bs2time, decode_bs2vram=self.decode_bs2vram)
        return machine_profile

    def get_max_num_layers(self) -> int:
        """
        Get the max number of layers that can be loaded into this machine.

        :return: max number of layers that can be loaded into the machine
        """
        return self.max_num_layers

    def get_inference_settings(self, num_on_node_layers: int) -> InferenceSettings:
        """
        Get the inference settings when there are given number of layers on node.
        Note: The inference settings are dependent on the number of layers.

        :param num_on_node_layers: number of layers on node
        :return: inference settings
        """
        assert 0 < num_on_node_layers <= self.max_num_layers, "Bad number of layers on node!"
        return self.num_layers_to_inference_settings[num_on_node_layers]

    def get_typical_token_throughput(self, num_on_node_layers: int) -> float:
        """
        Get typical token throughput when there are given number of layers on node.

        :param num_on_node_layers: number of layers on node
        :return: typical token throughput (in #tokens/s)
        """
        inference_settings = self.get_inference_settings(num_on_node_layers=num_on_node_layers)
        prompt_typical_requests = inference_settings.prompt_typical_requests
        prompt_typical_tokens = inference_settings.prompt_typical_tokens
        decode_typical_tokens = inference_settings.decode_typical_tokens

        # some helper functions
        from simulator.event_simulator.utils import linear_interpolate

        def _get_prompt_time(prompt_num_tokens: int) -> float:
            prompt_left, prompt_right = -1, 1000 * 1000
            for prompt_point in self.prompt_bs2time:
                if prompt_left < prompt_point <= prompt_num_tokens:
                    prompt_left = prompt_point
                if prompt_num_tokens <= prompt_point < prompt_right:
                    prompt_right = prompt_point
            return linear_interpolate(x_0=prompt_left, y_0=self.prompt_bs2time[prompt_left],
                                      x_1=prompt_right, y_1=self.prompt_bs2time[prompt_right],
                                      x_target=prompt_num_tokens)

        def _get_decode_time(decode_num_tokens: int) -> float:
            decode_left, decode_right = -1, 1000 * 1000
            for decode_point in self.decode_bs2time:
                if decode_left < decode_point <= decode_num_tokens:
                    decode_left = decode_point
                if decode_num_tokens <= decode_point < decode_right:
                    decode_right = decode_point
            return linear_interpolate(x_0=decode_left, y_0=self.decode_bs2time[decode_left],
                                      x_1=decode_right, y_1=self.decode_bs2time[decode_right],
                                      x_target=decode_num_tokens)

        # calculation method is dependent on prompt typical requests
        if prompt_typical_requests >= 1:
            # in linear region, no need to rescale
            total_tokens = prompt_typical_tokens + decode_typical_tokens
            layer_prompt_time = _get_prompt_time(prompt_num_tokens=prompt_typical_tokens)
            layer_decode_time = _get_decode_time(decode_num_tokens=decode_typical_tokens)
            total_time = num_on_node_layers * (layer_prompt_time + layer_decode_time)
            return total_tokens / total_time
        else:
            # need to scale to 1
            rescaling = 1 / prompt_typical_requests
            total_tokens = rescaling * (prompt_typical_tokens + decode_typical_tokens)
            layer_prompt_time = _get_prompt_time(prompt_num_tokens=int(prompt_typical_tokens * rescaling))
            layer_decode_time = _get_decode_time(decode_num_tokens=decode_typical_tokens) * rescaling
            total_time = num_on_node_layers * (layer_prompt_time + layer_decode_time)
            return total_tokens / total_time

    def get_kv_cache_capacity(self, num_on_node_layers: int) -> int:
        """
        Get the kv cache capacity of this machine when using the current model.

        :param num_on_node_layers: number of layers on node
        :return: kv cache capacity
        """
        return self.kv_cache_capacity[num_on_node_layers]

    def get_activation_backup_capacity(self, num_on_node_layers: int) -> int:
        """
        Get the activation backup capacity of this machine when using the current model.

        :param num_on_node_layers: number of layers on node
        :return: activation backup capacity
        """
        return self.activation_backup_capacity[num_on_node_layers]

