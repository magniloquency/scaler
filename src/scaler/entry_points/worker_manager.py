import dataclasses
from typing import Optional

from scaler.config.config_class import ConfigClass
from scaler.config.section.aws_hpc_worker_manager import AWSBatchWorkerManagerConfig
from scaler.config.section.ecs_worker_manager import ECSWorkerManagerConfig
from scaler.config.section.native_worker_manager import NativeWorkerManagerConfig
from scaler.config.section.orb_worker_adapter import ORBWorkerAdapterConfig
from scaler.config.section.symphony_worker_manager import SymphonyWorkerManagerConfig
from scaler.utility.logging.utility import setup_logger


@dataclasses.dataclass
class _WorkerManagerConfig(ConfigClass):
    native: Optional[NativeWorkerManagerConfig] = dataclasses.field(
        default=None, metadata=dict(subcommand="native_worker_manager")
    )
    symphony: Optional[SymphonyWorkerManagerConfig] = dataclasses.field(
        default=None, metadata=dict(subcommand="symphony_worker_manager")
    )
    ecs: Optional[ECSWorkerManagerConfig] = dataclasses.field(
        default=None, metadata=dict(subcommand="ecs_worker_manager")
    )
    hpc: Optional[AWSBatchWorkerManagerConfig] = dataclasses.field(
        default=None, metadata=dict(subcommand="aws_hpc_worker_manager")
    )
    orb: Optional[ORBWorkerAdapterConfig] = dataclasses.field(
        default=None, metadata=dict(subcommand="orb_worker_adapter")
    )


def main() -> None:
    config = _WorkerManagerConfig.parse("scaler_worker_manager", "")

    if config.native is not None:
        from scaler.worker_manager_adapter.baremetal.native import NativeWorkerManager

        setup_logger(
            config.native.logging_config.paths,
            config.native.logging_config.config_file,
            config.native.logging_config.level,
        )
        NativeWorkerManager(config.native).run()
    elif config.symphony is not None:
        from scaler.worker_manager_adapter.symphony.worker_manager import SymphonyWorkerManager

        setup_logger(
            config.symphony.logging_config.paths,
            config.symphony.logging_config.config_file,
            config.symphony.logging_config.level,
        )
        SymphonyWorkerManager(config.symphony).run()
    elif config.ecs is not None:
        from scaler.worker_manager_adapter.aws_raw.ecs import ECSWorkerManager

        setup_logger(
            config.ecs.logging_config.paths, config.ecs.logging_config.config_file, config.ecs.logging_config.level
        )
        ECSWorkerManager(config.ecs).run()
    elif config.hpc is not None:
        from scaler.worker_manager_adapter.aws_hpc.worker_manager import AWSHPCWorkerManager

        setup_logger(
            config.hpc.logging_config.paths, config.hpc.logging_config.config_file, config.hpc.logging_config.level
        )
        AWSHPCWorkerManager(config.hpc).run()
    elif config.orb is not None:
        from scaler.worker_manager_adapter.orb.worker_manager import ORBWorkerAdapter

        setup_logger(
            config.orb.logging_config.paths, config.orb.logging_config.config_file, config.orb.logging_config.level
        )
        ORBWorkerAdapter(config.orb).run()


if __name__ == "__main__":
    main()
