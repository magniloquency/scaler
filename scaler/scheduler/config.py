import dataclasses
import enum
from typing import Optional

from scaler.scheduler.allocate_policy.allocate_policy import AllocatePolicy
from scaler.utility.object_storage_config import ObjectStorageConfig
from scaler.utility.zmq_config import ZMQConfig


class TransportType(enum.Enum):
    YMQ = "YMQ"
    ZMQ = "ZMQ"

    @staticmethod
    def from_string(s: str) -> "TransportType":
        if s.lower() == "ymq":
            return TransportType.YMQ
        if s.lower() == "zmq":
            return TransportType.ZMQ
        raise ValueError(f"[{s}] is not a supported transport type")


@dataclasses.dataclass
class SchedulerConfig:
    event_loop: str
    address: ZMQConfig
    storage_address: Optional[ObjectStorageConfig]
    monitor_address: Optional[ZMQConfig]
    adapter_webhook_url: Optional[str]
    io_threads: int
    max_number_of_tasks_waiting: int
    client_timeout_seconds: int
    worker_timeout_seconds: int
    object_retention_seconds: int
    load_balance_seconds: int
    load_balance_trigger_times: int
    protected: bool
    allocate_policy: AllocatePolicy
    transport_type: TransportType
