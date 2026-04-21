import asyncio
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Awaitable, Callable, List, Tuple

from scaler.protocol.capnp import ProcessorStatus, Task, TaskCancel, WorkerManagerCommandResponse
from scaler.utility.identifiers import TaskID

if TYPE_CHECKING:
    from scaler.worker_manager_adapter.task_manager import TaskManager

Status = WorkerManagerCommandResponse.Status


class ProcessorStatusProvider(ABC):
    def set_task_manager(self, task_manager: "TaskManager") -> None:
        pass

    @abstractmethod
    def get_processor_statuses(self) -> List[ProcessorStatus]: ...


class ExecutionBackend(ABC):
    _load_task_inputs: Callable[[Task], Awaitable[Tuple[Any, List[Any]]]]

    def register(self, load_task_inputs: Callable[[Task], Awaitable[Tuple[Any, List[Any]]]]) -> None:
        self._load_task_inputs = load_task_inputs

    @abstractmethod
    async def execute(self, task: Task) -> asyncio.Future: ...

    async def on_cancel(self, task_cancel: TaskCancel) -> None:
        pass

    def on_cleanup(self, task_id: TaskID) -> None:
        pass

    async def routine(self) -> None:
        pass


class WorkerProvisioner(ABC):
    @abstractmethod
    async def start_worker(self) -> Tuple[List[bytes], Status]: ...

    @abstractmethod
    async def shutdown_workers(self, worker_ids: List[bytes]) -> Tuple[List[bytes], Status]: ...
