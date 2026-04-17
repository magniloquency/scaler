from typing import Dict, List, Optional, cast

from scaler.config.types.object_storage_server import ObjectStorageAddressConfig
from scaler.protocol.capnp import ProcessorStatus, Resource
from scaler.worker_manager_adapter.aws_hpc.task_manager import AWSHPCTaskManager
from scaler.worker_manager_adapter.base_heartbeat_manager import BaseHeartbeatManager


class AWSBatchHeartbeatManager(BaseHeartbeatManager):
    def __init__(
        self,
        object_storage_address: Optional[ObjectStorageAddressConfig],
        capabilities: Dict[str, int],
        task_queue_size: int,
        worker_manager_id: bytes,
    ) -> None:
        super().__init__(
            object_storage_address=object_storage_address,
            capabilities=capabilities,
            task_queue_size=task_queue_size,
            worker_manager_id=worker_manager_id,
        )

    def _get_processor_statuses(self) -> List:
        if self._task_manager is None:
            return []
        task_manager = cast(AWSHPCTaskManager, self._task_manager)
        processing_tasks = len(task_manager._processing_task_ids)
        return [
            ProcessorStatus(
                pid=0, initialized=True, hasTask=processing_tasks > 0, suspended=False, resource=Resource(cpu=0, rss=0)
            )
        ]
