import asyncio
import dataclasses
import enum
import logging
from typing import Any, Coroutine, Dict, List, Optional, Set, Tuple, Union, cast

import cloudpickle

from scaler import Serializer
from scaler.io.mixins import AsyncConnector, AsyncObjectStorageConnector
from scaler.protocol.capnp import (
    ObjectInstruction,
    ObjectMetadata,
    Task,
    TaskCancel,
    TaskCancelConfirm,
    TaskCancelConfirmType,
    TaskResult,
    TaskResultType,
)
from scaler.utility.identifiers import ObjectID, TaskID
from scaler.utility.metadata.task_flags import retrieve_task_flags_from_task
from scaler.utility.mixins import Looper
from scaler.utility.queues.async_priority_queue import AsyncPriorityQueue
from scaler.utility.serialization import serialize_failure
from scaler.worker.agent.mixins import HeartbeatManager
from scaler.worker.agent.mixins import TaskManager as TaskManagerMixin
from scaler.worker_manager.proxy.mixins import ExecutionBackend

logger = logging.getLogger(__name__)


class _TaskState(enum.Enum):
    QUEUED = enum.auto()
    STARTING = enum.auto()  # execute() is awaited, so the task has no future yet
    RUNNING = enum.auto()
    CANCELING = enum.auto()  # force-cancelled: its future, once it has one, is dropped rather than reported


@dataclasses.dataclass
class _TaskEntry:
    task: Task
    state: _TaskState
    holds_permit: bool = False
    future: Optional[asyncio.Future] = None


@dataclasses.dataclass(frozen=True)
class _TaskNew:
    task: Task


@dataclasses.dataclass(frozen=True)
class _CancelRequested:
    task_cancel: TaskCancel


@dataclasses.dataclass(frozen=True)
class _Started:
    task_id: TaskID
    future: asyncio.Future


@dataclasses.dataclass(frozen=True)
class _Finished:
    task_id: TaskID
    future: asyncio.Future


_Event = Union[_TaskNew, _CancelRequested, _Started, _Finished]


class TaskManager(Looper, TaskManagerMixin):
    """Owns every task on the worker. Only routine() reads or changes task state; everything else posts an event.

    upload_results() sends the results of finished tasks, so a slow upload does not hold up new tasks and cancels.
    """

    def __init__(self, base_concurrency: int, execution_backend: ExecutionBackend) -> None:
        if isinstance(base_concurrency, int) and base_concurrency <= 0:
            raise ValueError(f"base_concurrency must be a positive integer, got {base_concurrency}")

        self._base_concurrency = base_concurrency
        self._execution_backend = execution_backend

        self._events: asyncio.Queue[_Event] = asyncio.Queue()
        self._results: asyncio.Queue[Tuple[Task, asyncio.Future]] = asyncio.Queue()
        self._background_tasks: Set[asyncio.Task] = set()

        self._task_id_to_entry: Dict[TaskID, _TaskEntry] = dict()
        self._queued_task_id_queue = AsyncPriorityQueue()
        self._permits_held = 0

        self._serializers: Dict[bytes, Serializer] = dict()

        self._connector_external: Optional[AsyncConnector] = None
        self._connector_storage: Optional[AsyncObjectStorageConnector] = None
        self._heartbeat_manager: Optional[HeartbeatManager] = None

    def register(
        self,
        connector_external: AsyncConnector,
        connector_storage: AsyncObjectStorageConnector,
        heartbeat_manager: HeartbeatManager,
    ) -> None:
        self._connector_external = connector_external
        self._connector_storage = connector_storage
        self._heartbeat_manager = heartbeat_manager
        self._execution_backend.register(self.load_task_inputs)

    async def on_object_instruction(self, instruction: ObjectInstruction) -> None:
        if instruction.instructionType == ObjectInstruction.ObjectInstructionType.delete:
            for object_id in instruction.objectMetadata.objectIds:
                self._serializers.pop(object_id, None)
            return

        logger.error(f"worker received unknown object instruction type {instruction=}")

    async def on_task_new(self, task: Task) -> None:
        self._events.put_nowait(_TaskNew(task))

    async def on_cancel_task(self, task_cancel: TaskCancel) -> None:
        self._events.put_nowait(_CancelRequested(task_cancel))

    async def on_task_result(self, result: TaskResult) -> None:
        raise NotImplementedError("WorkerProcess never dispatches TaskResult to the proxy task manager")

    def get_queued_size(self) -> int:
        return self._queued_task_id_queue.qsize()

    def can_accept_task(self) -> bool:
        return self._permits_held < self._base_concurrency

    @property
    def processing_task_count(self) -> int:
        return sum(
            entry.state in (_TaskState.STARTING, _TaskState.RUNNING) for entry in self._task_id_to_entry.values()
        )

    async def routine(self) -> None:
        match await self._events.get():
            case _TaskNew(task):
                self._handle_task_new(task)
            case _CancelRequested(task_cancel):
                await self._handle_cancel(task_cancel)
            case _Started(task_id, future):
                self._handle_started(task_id, future)
            case _Finished(task_id, future):
                self._handle_finished(task_id, future)

    async def upload_results(self) -> None:
        task, future = await self._results.get()
        await self._send_task_result(task, future)

    def _handle_task_new(self, task: Task) -> None:
        task_priority = self._get_task_priority(task)
        entry = _TaskEntry(task=task, state=_TaskState.QUEUED)
        self._task_id_to_entry[task.taskId] = entry

        if self._permits_held == self._base_concurrency and all(
            task_priority > self._get_task_priority(other.task)
            for other in self._task_id_to_entry.values()
            if other.holds_permit
        ):
            # Bypass tasks intentionally exceed base_concurrency to service higher-priority requests immediately.
            self._start_task(entry, holds_permit=False)
            return

        self._queued_task_id_queue.put_nowait((-task_priority, task.taskId))
        self._start_queued_tasks()

    async def _handle_cancel(self, task_cancel: TaskCancel) -> None:
        task_id = task_cancel.taskId
        entry = self._task_id_to_entry.get(task_id)

        if entry is None or entry.state == _TaskState.CANCELING:
            await self._send_cancel_confirm(task_id, TaskCancelConfirmType.cancelNotFound)
            return

        if entry.state == _TaskState.QUEUED:
            self._queued_task_id_queue.remove(task_id)
            self._task_id_to_entry.pop(task_id)
            await self._send_cancel_confirm(task_id, TaskCancelConfirmType.canceled)
            return

        if not task_cancel.flags.force:
            await self._send_cancel_confirm(task_id, TaskCancelConfirmType.cancelFailed)
            return

        # A STARTING task has nothing to cancel in the backend yet: _handle_started cancels it once it does.
        if entry.state == _TaskState.RUNNING:
            self._spawn(self._cancel_in_backend(task_id, cast(asyncio.Future, entry.future)))

        entry.state = _TaskState.CANCELING
        await self._send_cancel_confirm(task_id, TaskCancelConfirmType.canceled)

    def _handle_started(self, task_id: TaskID, future: asyncio.Future) -> None:
        entry = self._task_id_to_entry[task_id]
        entry.future = future
        future.add_done_callback(lambda done: self._events.put_nowait(_Finished(task_id, done)))

        if entry.state == _TaskState.CANCELING:
            self._spawn(self._cancel_in_backend(task_id, future))
            return

        entry.state = _TaskState.RUNNING

    def _handle_finished(self, task_id: TaskID, future: asyncio.Future) -> None:
        entry = self._task_id_to_entry.pop(task_id)
        if entry.holds_permit:
            self._permits_held -= 1
        self._execution_backend.on_cleanup(task_id)
        self._start_queued_tasks()

        if entry.state == _TaskState.RUNNING:
            self._results.put_nowait((entry.task, future))

    def _start_queued_tasks(self) -> None:
        while self._permits_held < self._base_concurrency and self._queued_task_id_queue.qsize() > 0:
            _, task_id = self._queued_task_id_queue.get_nowait()
            self._start_task(self._task_id_to_entry[task_id], holds_permit=True)

    def _start_task(self, entry: _TaskEntry, holds_permit: bool) -> None:
        entry.state = _TaskState.STARTING
        entry.holds_permit = holds_permit
        if holds_permit:
            self._permits_held += 1
        self._spawn(self._execute(entry.task))

    def _spawn(self, coroutine: Coroutine[Any, Any, None]) -> None:
        background_task = asyncio.get_running_loop().create_task(coroutine)
        self._background_tasks.add(background_task)
        background_task.add_done_callback(self._background_tasks.discard)

    async def _execute(self, task: Task) -> None:
        try:
            future = await self._execution_backend.execute(task)
        except Exception as exc:
            logger.exception(f"Failed to start task: task_id={task.taskId.hex()}")
            future = asyncio.get_running_loop().create_future()
            future.set_exception(exc)

        self._events.put_nowait(_Started(task.taskId, future))

    async def _cancel_in_backend(self, task_id: TaskID, future: asyncio.Future) -> None:
        try:
            await self._execution_backend.on_cancel(
                TaskCancel(taskId=task_id, flags=TaskCancel.TaskCancelFlags(force=True))
            )
        except Exception:
            logger.exception(f"Failed to cancel task in the backend: task_id={task_id.hex()}")

        future.cancel()

    async def _send_task_result(self, task: Task, future: asyncio.Future) -> None:
        if future.exception() is None:
            serializer_id = ObjectID.generate_serializer_object_id(task.source)
            serializer = self._serializers[serializer_id]
            result_bytes = serializer.serialize(future.result())
            result_type = TaskResultType.success
        else:
            result_bytes = serialize_failure(cast(Exception, future.exception()))
            result_type = TaskResultType.failed

        result_object_id = ObjectID.generate_object_id(task.source)

        await self._connector_storage.set_object(result_object_id, result_bytes)
        await self._connector_external.send(
            ObjectInstruction(
                instructionType=ObjectInstruction.ObjectInstructionType.create,
                objectUser=task.source,
                objectMetadata=ObjectMetadata(
                    objectIds=(result_object_id,),
                    objectTypes=(ObjectMetadata.ObjectContentType.object,),
                    objectNames=(f"<res {result_object_id.hex()[:6]}>".encode(),),
                ),
            ),
            detached=True,
        )

        await self._connector_external.send(
            TaskResult(taskId=task.taskId, resultType=result_type, metadata=b"", results=[bytes(result_object_id)]),
            detached=True,
        )

    async def _send_cancel_confirm(self, task_id: TaskID, cancel_confirm_type: TaskCancelConfirmType) -> None:
        await self._connector_external.send(
            TaskCancelConfirm(taskId=task_id, cancelConfirmType=cancel_confirm_type), detached=True
        )

    async def load_task_inputs(self, task: Task) -> Tuple[Any, List[Any]]:
        serializer_id = ObjectID.generate_serializer_object_id(task.source)

        if serializer_id not in self._serializers:
            serializer_bytes = await self._connector_storage.get_object(serializer_id)
            serializer = cloudpickle.loads(serializer_bytes)
            self._serializers[serializer_id] = serializer
        else:
            serializer = self._serializers[serializer_id]

        get_tasks = [
            self._connector_storage.get_object(object_id)
            for object_id in [ObjectID(task.funcObjectId), *(ObjectID(argument.data) for argument in task.functionArgs)]
        ]

        function_bytes, *arg_bytes = await asyncio.gather(*get_tasks)

        function = serializer.deserialize(function_bytes)
        arg_objects = [serializer.deserialize(object_bytes) for object_bytes in arg_bytes]
        return function, arg_objects

    @staticmethod
    def _get_task_priority(task: Task) -> int:
        priority = retrieve_task_flags_from_task(task).priority

        if priority < 0:
            raise ValueError(f"invalid task priority, must be positive or zero, got {priority}")

        return priority
