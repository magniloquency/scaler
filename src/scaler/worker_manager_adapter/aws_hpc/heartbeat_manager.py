from typing import TYPE_CHECKING, List, Optional

from scaler.protocol.capnp import ProcessorStatus, Resource
from scaler.worker_manager_adapter.mixins import ProcessorStatusProvider

if TYPE_CHECKING:
    from scaler.worker_manager_adapter.task_manager import TaskManager


class AWSProcessorStatusProvider(ProcessorStatusProvider):
    def __init__(self) -> None:
        self._task_manager: Optional["TaskManager"] = None

    def set_task_manager(self, task_manager: "TaskManager") -> None:
        self._task_manager = task_manager

    def get_processor_statuses(self) -> List[ProcessorStatus]:
        if self._task_manager is None:
            return []

        processing_tasks = self._task_manager.processing_task_count
        return [
            ProcessorStatus(
                pid=0, initialized=True, hasTask=processing_tasks > 0, suspended=False, resource=Resource(cpu=0, rss=0)
            )
        ]
