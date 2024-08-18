from typing import Any, Dict, Optional, Union, List
from substrateinterface import Keypair
from pydantic import BaseModel, Field, PrivateAttr, ConfigDict
from pathlib import Path
import argparse
import json
import os
import yaml
import copy
import sys

from munch import DefaultMunch


class Config(BaseModel):
    config: Optional[Union[Dict[str, Any], object]] = None
    _is_set: Dict[str, Dict[str, bool]] = PrivateAttr(default_factory=dict)

    def __init__(self, **data):
        super().__init__(**data)
        self._is_set = data.get('_is_set', {})

    def get(self, key: str, default: Any = ...) -> Any:
        keys = key.split('.')
        value = self
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            elif isinstance(value, BaseModel):
                value = getattr(value, k, None)
            else:
                return default if default is not ... else None
            if value is None:
                return default if default is not ... else None
        return value
    
    def is_set(self, key: str) -> bool:
        keys = key.split('.')
        is_set_dict = self._is_set
        for k in keys:
            if k not in is_set_dict:
                return False
            if isinstance(is_set_dict[k], bool):
                return is_set_dict[k]
            is_set_dict = is_set_dict[k]
        return True
    
    def set_is_set(self, key: str, value: bool):
        keys = key.split('.')
        is_set_dict = self._is_set
        for k in keys[:-1]:
            if k not in is_set_dict:
                is_set_dict[k] = {}
            is_set_dict = is_set_dict[k]
        is_set_dict[keys[-1]] = value
        
    @classmethod
    def merge(cls, a, b=None):
        if not b:
            b = {}
        for key in b:
            if key in a and isinstance(a[key], dict) and isinstance(b[key], dict):
                cls.merge(a[key], b[key])
            else:
                a[key] = b[key]
        return a
    
    
class WalletConfig(Config):
    name: str
    hotkey: Optional[str] = None
    path: str
    model_config: ConfigDict = ConfigDict(
        {"arbitrary_types_allowed": True}
    )
    

class AxonConfig(Config):
    port: int
    ip: str
    external_ip: str
    external_port: int
    max_workers: int


class SubtensorConfig(Config):
    network: str
    chain_endpoint: str


class MinerConfig(Config):
    root: str
    name: str
    blocks_per_epoch: int
    no_serve: bool
    no_start_axon: bool
    mock_subtensor: bool
    full_path: str


class LoggingConfig(Config):
    debug: bool
    trace: bool
    record_log: bool
    logging_dir: str


class Configuration(Config):
    axon: Optional[AxonConfig] = None
    wallet: Optional[WalletConfig] = None
    subtensor: Optional[SubtensorConfig] = None
    miner: Optional[MinerConfig] = None
    logging: Optional[LoggingConfig] = None
    netuid: Optional[int] = None
    no_prompt: Optional[bool] = None
    strict: Optional[bool] = None
    no_version_checking: Optional[bool] = None
    model_config: ConfigDict = ConfigDict({
        "arbitrary_types_allowed": True
    })


class bittensor_config(DefaultMunch):
    config: Configuration = Field(default_factory=Configuration)
    lines: List[Any] = []

    def __init__(self, parser=None, args=None, strict=False, default=None):
        super().__init__(default)

        if parser is None:
            parser = argparse.ArgumentParser(description="Bittensor Configuration")
        self.config = self.cli()
        print(self.config)
        self.write_environment()
        self._add_args(parser)
        # Parse arguments
        args = sys.argv[1:] if args is None else args
        if args:

            config_params = self.__parse_args__(args, parser, False)

            # Load config from file if specified
            self._load_config_file(parser, args)

            # Parse arguments again with potential new defaults
            params = self.__parse_args__(args, parser, config_params.strict or strict)

            # Split params and add to config
            self.__split_params__(params, self.config)

            # Track which parameters are set
            self._track_set_parameters(parser, args, params)

    def __getitem__(self, key):
        return self.config.get(key)

    def __setitem__(self, key, value):
        keys = key.split('.')
        obj = self.config
        for k in keys[:-1]:
            if not hasattr(obj, k):
                setattr(obj, k, Configuration())
            obj = getattr(obj, k)
        setattr(obj, keys[-1], value)

    def get(self, key, default: Any = ...) -> Any:
        if not self.config:
            self.config = self.cli()
        if key == "config":
            return self.config
        if key in self.config:
            return self.config.get(key)
        else:
            self.config.__setattr__(key, default)
            return default

    def _track_set_parameters(self, parser, args, params):
        parser_no_defaults = copy.deepcopy(parser)
        parser_no_defaults.set_defaults(**{key: argparse.SUPPRESS for key in params.__dict__})
        params_no_defaults = self.__parse_args__(args, parser_no_defaults, False)
        self.config._is_set = {k: True for k, v in params_no_defaults.__dict__.items() if v != argparse.SUPPRESS}

    def _load_config_file(self, parser, args):
        if self.config is None:
            self.config = self.cli()
            self._add_args(parser, args)
        return self.config

    @staticmethod
    def __parse_args__(args, parser, strict):
        if not strict:
            params, unrecognized = parser.parse_known_args(args=args)
            for unrec in unrecognized:
                if unrec.startswith("--") and unrec[2:] in params.__dict__:
                    setattr(params, unrec[2:], True)
        else:
            params = parser.parse_args(args=args)
        return params

           
    @staticmethod
    def __split_params__(params, _config):
        for arg_key, arg_val in params.__dict__.items():
            keys = arg_key.split(".")
            head = _config
            for key in keys[:-1]:
                if not hasattr(head, key):
                    setattr(head, key, Configuration())
                head = getattr(head, key)
            setattr(head, keys[-1], arg_val)

    def __deepcopy__(self, memo):
        config_copy = bittensor_config()
        memo[id(self)] = config_copy
        for k, v in self.items():
            if k == 'config':
                config_copy.config = Configuration(**copy.deepcopy(v.__dict__, memo))
            else:
                setattr(config_copy, k, copy.deepcopy(v, memo))
        return config_copy

    def __str__(self):
        visible = copy.deepcopy(self.toDict())
        visible.pop("__parser", None)
        visible.pop("__is_set", None)
        return "\n" + yaml.dump(visible, sort_keys=False)

    def _add_args(self, parser: argparse.ArgumentParser):
        parser.add_argument("--subtensor.network", default=f"{os.getenv('subtensor_network')}")
        parser.add_argument("--subtensor.chain_endpoint", default=f"{os.getenv('subtensor_chain_endpoint')}")
        parser.add_argument("--netuid", default=f"{os.getenv('netuid')}")
        parser.add_argument("--miner.name", default=f"{os.getenv('miner_name')}")
        parser.add_argument("--miner.blocks_per_epoch", default=f"{os.getenv('miner_blocks_per_epoch')}")
        parser.add_argument("--miner.no_serve", default=f"{os.getenv('miner_no_serve')}")
        parser.add_argument("--miner.no_start_axon", default=f"{os.getenv('miner_no_start_axon')}")
        parser.add_argument("--miner.mock_subtensor", default=f"{os.getenv('miner_mock_subtensor')}")
        parser.add_argument("--logging.debug", default=f"{os.getenv('logging_debug')}")
        parser.add_argument("--logging.trace", default=f"{os.getenv('logging_trace')}")
        parser.add_argument("--logging.record_log", default=f"{os.getenv('logging_record_log')}")
        parser.add_argument("--logging.logging_dir", default=f"{os.getenv('logging_logging_dir')}")
        parser.add_argument("--no_prompt", default=f"{os.getenv('no_prompt')}")
        parser.add_argument("--wallet.name", default=f"{os.getenv('wallet_name')}")
        parser.add_argument("--wallet.hotkey", default=f"{os.getenv('wallet_hotkey')}")
        parser.add_argument("--wallet.path", default=f"{os.getenv('wallet_path')}")
        parser.add_argument("--axon.port", default=f"{os.getenv('axon_port')}")
        parser.add_argument("--axon.ip", default=f"{os.getenv('axon_ip')}")
        parser.add_argument("--axon.external_port", default=f"{os.getenv('axon_port')}")
        parser.add_argument("--axon.external_ip", default=f"{os.getenv('axon_external_ip')}")
        parser.add_argument("--axon.max_workers", default=f"{os.getenv('axon_max_workers')}")
        parser.add_argument("--miner.full_path", default=f"{os.getenv('miner_full_path')}")
        parser.add_argument("--strict", default=f"{os.getenv('strict')}")
        parser.add_argument('--netuid', default=f'{os.getenv("NETUID")}')
        parser.add_argument('--neuron.device', default=f'{os.getenv("NEURON_DEVICE")}')
        parser.add_argument('--neuron.epoch_length', default=f'{os.getenv("NEURON_EPOCH_LENGTH")}')
        parser.add_argument('--mock', default=f'{os.getenv("MOCK")}')
        parser.add_argument('--neuron.events_retention_size', default=f'{os.getenv("NEURON_EVENTS_RETENTION_SIZE")}')
        parser.add_argument('--neuron.dont_save_events', default=f'{os.getenv("NEURON_DONT_SAVE_EVENTS")}')
        parser.add_argument('--wandb.off', default=f'{os.getenv("WANDB_OFF")}')
        parser.add_argument('--wandb.offline', default=f'{os.getenv("WANDB_OFFLINE")}')
        parser.add_argument('--wandb.notes', default=f'{os.getenv("WANDB_NOTES")}')
        parser.add_argument('--neuron.name', default=f'{os.getenv("NEURON_NAME")}')
        parser.add_argument('--blacklist.force_validator_permit', default=f'{os.getenv("BLACKLIST_FORCE_VALIDATOR_PERMIT")}')
        parser.add_argument('--blacklist.allow_non_registered', default=f'{os.getenv("BLACKLIST_ALLOW_NON_REGISTERED")}')
        parser.add_argument('--wandb.project_name', default=f'{os.getenv("WANDB_PROJECT_NAME")}')
        parser.add_argument('--wandb.entity', default=f'{os.getenv("WANDB_ENTITY")}')
        parser.add_argument('--neuron.name', default=f'{os.getenv("NEURON_NAME")}')
        parser.add_argument('--neuron.timeout', default=f'{os.getenv("NEURON_TIMEOUT")}')
        parser.add_argument('--neuron.num_concurrent_forwards', default=f'{os.getenv("NEURON_NUM_CONCURRENT_FORWARDS")}')
        parser.add_argument('--neuron.sample_size', default=f'{os.getenv("NEURON_SAMPLE_SIZE")}')
        parser.add_argument('--neuron.disable_set_weights', default=f'{os.getenv("NEURON_DISABLE_SET_WEIGHTS")}')
        parser.add_argument('--neuron.moving_average_alpha', default=f'{os.getenv("NEURON_MOVING_AVERAGE_ALPHA")}')
        parser.add_argument('--neuron.axon_off', default=f'{os.getenv("NEURON_AXON_OFF")}')
        parser.add_argument('--neuron.vpermit_tao_limit', default=f'{os.getenv("NEURON_VPERMIT_TAO_LIMIT")}')
        parser.add_argument('--wandb.project_name', default=f'{os.getenv("WANDB_PROJECT_NAME")}')
        parser.add_argument('--wandb.entity', default=f'{os.getenv("WANDB_ENTITY")}')
        return parser

    def _add_env_variables(self):
        self.lines = [
            f"BT_AXON_PORT={self.config.axon.port}",
            f"BT_AXON_IP={self.config.axon.ip}",
            f"BT_AXON_EXTERNAL_PORT={self.config.axon.external_port}",
            f"BT_AXON_EXTERNAL_IP={self.config.axon.external_ip}",
            f"BT_AXON_MAX_WORERS={self.config.axon.max_workers}",
            f"BT_PRIORITY_MAX_WORKERS={self.config.axon.max_workers}",
            "BT_PRIORITY_MAXSIZE=5000",
            f"BT_WALLET_NAME={self.config.wallet.name}",
            f"BT_WALLET_HOTKEY={self.config.wallet.hotkey}",
            f"BT_WALLET_PATH={self.config.wallet.path}",
            "NETUID=197",
            "NEURON_DEVICE=cuda(0)",
            "NEURON_EPOCH_LENGTH=100",
            "MOCK=False",
            "NEURON_EVENTS_RETENTION_SIZE=2 * 1024 * 1024 * 1024",
            "NEURON_DONT_SAVE_EVENTS=False",
            "WANDB_OFF=True",
            "WANDB_OFFLINE=False",
            "WANDB_NOTES=",
            "NEURON_NAME=miner",
            "BLACKLIST_FORCE_VALIDATOR_PERMIT=False",
            "BLACKLIST_ALLOW_NON_REGISTERED=False",
            "WANDB_PROJECT_NAME=template-miners",
            "WANDB_ENTITY=opentensor-dev",
            "NEURON_NAME=razor_test",
            "NEURON_TIMEOUT=10",
            "NEURON_NUM_CONCURRENT_FORWARDS=1",
            "NEURON_SAMPLE_SIZE=50",
            "NEURON_DISABLE_SET_WEIGHTS=False",
            "NEURON_MOVING_AVERAGE_ALPHA=0.1",
            "NEURON_AXON_OFF=False",
            "NEURON_VPERMIT_TAO_LIMIT=4096",
            "WANDB_PROJECT_NAME=template-validators",
            "WANDB_ENTITY=opentensor-dev"
        ]
        return self.lines

    def cli(self):
        configure = input("Do you want to setup Bittensor configuration? (y/n) ")
        
        if configure.lower() == 'y':
            port = int(input("Enter axon port[8080]: ") or 8080)
            ip = input("Enter axon ip[0.0.0.0]: ") or "0.0.0.0"
            external_ip = input("Enter axon external ip[0.0.0.0]: ") or "0.0.0.0"
            external_port = int(input("Enter axon external port[8080]: ") or 8080)
            max_workers = int(input("Enter max workers[10]: ") or 10)
            network = input("Enter subtensor network(finney/[testnet]/local): ") or "test"
            chain_endpoint = input("Enter chain endpoint[wss://test.opentensor.ai:443]: ") or "wss://test.finney.opentensor.ai:443"
            root = input("Enter miner root[/home/user/.bittensor/miners/razor_test/]: ") or "/home/user/.bittensor/miners/razor_test/"
            name = input("Enter miner name[razor_hot]: ") or "razor_hot"
            blocks_per_epoch = int(input("Enter blocks per epoch[100]: ") or 100)
            no_serve = bool(input("Enter no_serve[False]: ") or False)
            no_start_axon = bool(input("Enter no_start_axon[False]: ") or False)
            mock_subtensor = bool(input("Enter mock_subtensor[False]: ") or False)
            full_path = input("Enter full_path[/home/user/.bittensor/miners/razor_test/razor_hot/netuid197/razor_test]: ") or "/home/user/.bittensor/miners/razor_test/razor_hot/netuid197/razor_test"
            debug = bool(input("Enter debug[True]: ") or True)
            trace = bool(input("Enter trace[True]: ") or True)
            record_log = bool(input("Enter record_log[True]: ") or True)
            logging_dir = input("Enter logging_dir[/home/user/vscode/module_validator/.log]: ") or "/home/user/vscode/module_validator/.log"
            name = input("Enter wallet name[razor_test]: ") or "razor_test"
            hotkey = input("Enter wallet hotkey[razor_hot]: ") or "razor_hot"
            path = input("Enter wallet path[/home/user/.bittensor/wallets]: ") or "/home/user/.bittensor/wallets"
            netuid = int(input("Enter netuid[197]: ") or 197)
            no_prompt = bool(input("Enter no_prompt[False]: ") or False)
            strict = bool(input("Enter strict[False]: ") or False)
            no_version_checking = bool(input("Enter no_version_checking[False]: ") or False)
        else:
            port = int(os.getenv("axon_port") or 8080)
            ip = os.getenv("axon_ip") or "0.0.0.0"
            external_ip = os.getenv("axon_external_ip") or "0.0.0.0"
            external_port = int(os.getenv("axon_external_port") or 8080)
            max_workers = int(os.getenv("axon_max_workers") or 8)
            network = os.getenv("subtensor_network") or "test"
            chain_endpoint = os.getenv("subtensor_chain_endpoint") or "wss://entrypoint-finney.opentensor.ai:443"
            root = os.getenv("miner_root") or "/home/user/.bittensor/miners/razor_test/"
            name = os.getenv("miner_name") or "razor_hot"
            blocks_per_epoch = os.getenv("miner_blocks_per_epoch") or 100
            no_serve = os.getenv("miner_no_serve") or False
            no_start_axon = os.getenv("miner_no_start_axon") or False
            mock_subtensor = os.getenv("miner_mock_subtensor") or False
            full_path = os.getenv("full_path") or "/home/bakobi/.bittensor/miners/razor_test/razor_hot/netuid197/razor_test"
            debug = os.getenv("logging_debug") or True
            trace = os.getenv("logging_trace") or True
            record_log = os.getenv("logging_record_log") or True
            logging_dir = os.getenv("logging_logging_dir") or "/home/bakobi/vscode/module_validator/.log"
            name = os.getenv("wallet_name") or "razor_test"
            hotkey = os.getenv("wallet_hotkey") or "razor_hot"
            path = os.getenv("wallet_path") or "/home/bakobi/.bittensor/wallets"
            netuid = int(os.getenv("netuid") or 197)
            no_prompt = bool(os.getenv("no_prompt") or False)
            strict = bool(os.getenv("strict") or False)
            no_version_checking = os.getenv("no_version_checking") or False
            
        return Configuration(
            axon=AxonConfig(
                port=port,
                ip=ip,
                external_ip=external_ip,
                external_port=external_port,
                max_workers=max_workers
            ),
            subtensor=SubtensorConfig(
                network=network,
                chain_endpoint=chain_endpoint
            ),
            miner=MinerConfig(
                root=root,
                name=name,
                blocks_per_epoch=blocks_per_epoch,
                no_serve=no_serve,
                no_start_axon=no_start_axon,
                mock_subtensor=mock_subtensor,
                full_path=full_path
            ),
            logging=LoggingConfig(
                debug=debug,
                trace=trace,
                record_log=record_log,
                logging_dir=logging_dir,
            ),
            wallet=WalletConfig(
                name=name,
                hotkey=hotkey,
                path=path,
            ),
            netuid=netuid,
            no_prompt=no_prompt,
            strict=strict,
            no_version_checking=no_version_checking,
        )

    def get_hotkey(self, wallet_name: str, hotkey_name: str):
        path = Path("~/.bittensor/wallets").expanduser()
        key_path =  path / wallet_name / "hotkeys" / hotkey_name
        key_data = json.loads(key_path.read_text())
        public_key = key_data["publicKey"]
        private_key = key_data["privateKey"]
        ss58key = key_data["ss58Address"]
        return Keypair(ss58_address=ss58key, private_key=private_key, public_key=public_key)
        
    def write_environment(self):
        settings = self.config
        settings_dict = {}
        if isinstance(settings, Configuration):
            settings_dict = settings.model_dump()

        env_dict = {}

        for key, value in settings_dict.items():
            if isinstance(value, Configuration):
                value = value.model_dump()
            if isinstance(value, dict):
                for subkey, subvalue in value.items():
                    env_dict[f"{key}_{subkey}"] = subvalue
            else:
                env_dict[key] = value

        lines = [f"{key}={value}\n" for key, value in env_dict.items()]
        lines.extend([f"{variable}\n" for variable in self._add_env_variables()])
        with open(".env", "w", encoding="utf-8") as f:
            f.writelines(lines)
        return settings_dict


def main():
    parser = argparse.ArgumentParser(description="bittensor configuration")
    configuration = bittensor_config(parser=parser)
    print(configuration.config)
    return configuration.config
    

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    configuration = bittensor_config(parser=parser)
    
    print(configuration.config)