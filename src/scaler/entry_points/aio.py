import dataclasses
import multiprocessing
import sys
from typing import List, Optional

from scaler.config.config_class import ConfigClass
from scaler.config.section.aws_hpc_worker_manager import AWSBatchWorkerManagerConfig
from scaler.config.section.ecs_worker_manager import ECSWorkerManagerConfig
from scaler.config.section.native_worker_manager import NativeWorkerManagerConfig
from scaler.config.section.orb_worker_adapter import ORBWorkerAdapterConfig
from scaler.config.section.scheduler import SchedulerConfig
from scaler.config.section.symphony_worker_manager import SymphonyWorkerManagerConfig
from scaler.utility.logging.utility import setup_logger


@dataclasses.dataclass
class _AIOConfig(ConfigClass):
    # Declaration order = startup order (scheduler before workers).
    scheduler: Optional[SchedulerConfig] = dataclasses.field(default=None, metadata=dict(section="scheduler"))
    native_worker_manager: List[NativeWorkerManagerConfig] = dataclasses.field(
        default_factory=list, metadata=dict(section="native_worker_manager")
    )
    symphony_worker_manager: List[SymphonyWorkerManagerConfig] = dataclasses.field(
        default_factory=list, metadata=dict(section="symphony_worker_manager")
    )
    ecs_worker_manager: List[ECSWorkerManagerConfig] = dataclasses.field(
        default_factory=list, metadata=dict(section="ecs_worker_manager")
    )
    aws_hpc_worker_manager: List[AWSBatchWorkerManagerConfig] = dataclasses.field(
        default_factory=list, metadata=dict(section="aws_hpc_worker_manager")
    )
    orb_worker_adapter: List[ORBWorkerAdapterConfig] = dataclasses.field(
        default_factory=list, metadata=dict(section="orb_worker_adapter")
    )


# --- per-type runners (module-level for multiprocessing spawn compatibility) ---


def _run_scheduler(config: SchedulerConfig) -> None:
    from scaler.entry_points.scheduler import main as _main

    _main(config)


def _run_native(config: NativeWorkerManagerConfig) -> None:
    from scaler.worker_manager_adapter.baremetal.native import NativeWorkerManager

    setup_logger(config.logging_config.paths, config.logging_config.config_file, config.logging_config.level)
    NativeWorkerManager(config).run()


def _run_symphony(config: SymphonyWorkerManagerConfig) -> None:
    from scaler.worker_manager_adapter.symphony.worker_manager import SymphonyWorkerManager

    setup_logger(config.logging_config.paths, config.logging_config.config_file, config.logging_config.level)
    SymphonyWorkerManager(config).run()


def _run_ecs(config: ECSWorkerManagerConfig) -> None:
    from scaler.worker_manager_adapter.aws_raw.ecs import ECSWorkerManager

    setup_logger(config.logging_config.paths, config.logging_config.config_file, config.logging_config.level)
    ECSWorkerManager(config).run()


def _run_hpc(config: AWSBatchWorkerManagerConfig) -> None:
    from scaler.worker_manager_adapter.aws_hpc.worker_manager import AWSHPCWorkerManager

    setup_logger(config.logging_config.paths, config.logging_config.config_file, config.logging_config.level)
    AWSHPCWorkerManager(config).run()


def _run_orb(config: ORBWorkerAdapterConfig) -> None:
    from scaler.worker_manager_adapter.orb.worker_manager import ORBWorkerAdapter

    setup_logger(config.logging_config.paths, config.logging_config.config_file, config.logging_config.level)
    ORBWorkerAdapter(config).run()


def main() -> None:
    config = _AIOConfig.parse("scaler_aio", "aio")

    processes: List[multiprocessing.Process] = []

    if config.scheduler is not None:
        processes.append(multiprocessing.Process(target=_run_scheduler, args=(config.scheduler,), name="scheduler"))
    for native_cfg in config.native_worker_manager:
        processes.append(multiprocessing.Process(target=_run_native, args=(native_cfg,), name="native_worker_manager"))
    for symphony_cfg in config.symphony_worker_manager:
        processes.append(
            multiprocessing.Process(target=_run_symphony, args=(symphony_cfg,), name="symphony_worker_manager")
        )
    for ecs_cfg in config.ecs_worker_manager:
        processes.append(multiprocessing.Process(target=_run_ecs, args=(ecs_cfg,), name="ecs_worker_manager"))
    for hpc_cfg in config.aws_hpc_worker_manager:
        processes.append(multiprocessing.Process(target=_run_hpc, args=(hpc_cfg,), name="aws_hpc_worker_manager"))
    for orb_cfg in config.orb_worker_adapter:
        processes.append(multiprocessing.Process(target=_run_orb, args=(orb_cfg,), name="orb_worker_adapter"))

    if not processes:
        print("scaler_aio: no recognized sections found in config file", file=sys.stderr)
        sys.exit(1)

    for process in processes:
        process.start()

    for process in processes:
        process.join()


if __name__ == "__main__":
    main()
