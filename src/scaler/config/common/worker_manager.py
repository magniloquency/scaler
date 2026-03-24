import dataclasses
from typing import Optional

from scaler.config import defaults
from scaler.config.config_class import ConfigClass
from scaler.config.types.object_storage_server import ObjectStorageAddressConfig
from scaler.config.types.zmq import ZMQConfig


@dataclasses.dataclass
class WorkerManagerConfig(ConfigClass):
    scheduler_address: ZMQConfig = dataclasses.field(
        metadata=dict(positional=True, required=True, help="scheduler address to connect workers to")
    )

    worker_manager_id: str = dataclasses.field(
        metadata=dict(short="-wmi", required=True, help="worker manager ID to identify this manager")
    )

    object_storage_address: Optional[ObjectStorageAddressConfig] = dataclasses.field(
        default=None,
        metadata=dict(short="-osa", help="specify the object storage server address, e.g.: tcp://localhost:2346"),
    )

    max_task_concurrency: int = dataclasses.field(
        default=defaults.DEFAULT_MAX_TASK_CONCURRENCY,
        metadata=dict(
            short="-mtc",
            help=(
                "maximum number of workers that can be started, -1 means no limit."
                "for fixed native worker manager, this is exactly the number of workers that will be spawned"
            ),
        ),
    )

    preload: Optional[str] = dataclasses.field(
        default=None,
        metadata=dict(help="preload function spec executed on worker init, e.g. 'pkg.mod:func(arg1, kw=val)'"),
    )

    def __post_init__(self) -> None:
        if not self.worker_manager_id:
            raise ValueError("worker_manager_id cannot be an empty string.")
        if self.max_task_concurrency != -1 and self.max_task_concurrency < 0:
            raise ValueError("max_task_concurrency must be -1 (no limit) or a non-negative integer.")
