from typing import Dict, List, Optional

from scaler.config.types.object_storage_server import ObjectStorageAddressConfig
from scaler.worker_manager_adapter.base_heartbeat_manager import BaseHeartbeatManager


class SymphonyHeartbeatManager(BaseHeartbeatManager):
    def __init__(
        self,
        object_storage_address: Optional[ObjectStorageAddressConfig],
        capabilities: Dict[str, int],
        task_queue_size: int,
        worker_manager_id: bytes,
    ):
        super().__init__(
            object_storage_address=object_storage_address,
            capabilities=capabilities,
            task_queue_size=task_queue_size,
            worker_manager_id=worker_manager_id,
        )

    def _get_processor_statuses(self) -> List:
        return []
