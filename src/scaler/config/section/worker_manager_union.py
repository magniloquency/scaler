from typing import Union

from scaler.config.section.aws_hpc_worker_manager import AWSBatchWorkerManagerConfig
from scaler.config.section.ecs_worker_manager import ECSWorkerManagerConfig
from scaler.config.section.native_worker_manager import NativeWorkerManagerConfig
from scaler.config.section.orb_worker_adapter import ORBWorkerAdapterConfig
from scaler.config.section.symphony_worker_manager import SymphonyWorkerManagerConfig

WorkerManagerUnion = Union[
    NativeWorkerManagerConfig,
    SymphonyWorkerManagerConfig,
    ECSWorkerManagerConfig,
    AWSBatchWorkerManagerConfig,
    ORBWorkerAdapterConfig,
]
