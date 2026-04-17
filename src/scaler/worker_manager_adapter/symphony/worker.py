from typing import Dict, Optional

from scaler.config.types.object_storage_server import ObjectStorageAddressConfig
from scaler.config.types.zmq import ZMQConfig
from scaler.worker_manager_adapter.base_heartbeat_manager import BaseHeartbeatManager
from scaler.worker_manager_adapter.base_task_manager import BaseTaskManager
from scaler.worker_manager_adapter.base_worker import BaseWorker
from scaler.worker_manager_adapter.symphony.heartbeat_manager import SymphonyHeartbeatManager
from scaler.worker_manager_adapter.symphony.task_manager import SymphonyTaskManager


class SymphonyWorker(BaseWorker):
    """
    SymphonyWorker handles multiple concurrent tasks via SymphonyTaskManager.
    """

    def __init__(
        self,
        name: str,
        address: ZMQConfig,
        object_storage_address: Optional[ObjectStorageAddressConfig],
        service_name: str,
        capabilities: Dict[str, int],
        base_concurrency: int,
        heartbeat_interval_seconds: int,
        death_timeout_seconds: int,
        task_queue_size: int,
        io_threads: int,
        event_loop: str,
        worker_manager_id: bytes,
    ):
        super().__init__(
            name=name,
            address=address,
            object_storage_address=object_storage_address,
            capabilities=capabilities,
            base_concurrency=base_concurrency,
            heartbeat_interval_seconds=heartbeat_interval_seconds,
            death_timeout_seconds=death_timeout_seconds,
            task_queue_size=task_queue_size,
            io_threads=io_threads,
            event_loop=event_loop,
            worker_manager_id=worker_manager_id,
        )
        self._service_name = service_name

    def _create_heartbeat_manager(self) -> BaseHeartbeatManager:
        return SymphonyHeartbeatManager(
            object_storage_address=self._object_storage_address,
            capabilities=self._capabilities,
            task_queue_size=self._task_queue_size,
            worker_manager_id=self._worker_manager_id,
        )

    def _create_task_manager(self) -> BaseTaskManager:
        return SymphonyTaskManager(base_concurrency=self._base_concurrency, service_name=self._service_name)
