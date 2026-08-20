"""Drives ``VanillaProcessorManager`` and ``VanillaTaskManager`` together with stubbed processors.

A processor that dies while suspended is cleaned up by ``on_failing_processor``, which awaits the object storage
and the scheduler connector before it tells the task manager that the task is over. The worker's own task routine
can run inside that window, and it will pick the very same suspended task off its queue. This test pins the
invariant that has to survive that meeting: the worker never leaves the accept-task lock closed while no processor
is running anything, because nothing would ever reopen it and the worker would keep being assigned tasks it can
never start.
"""

import asyncio
import unittest
import unittest.mock
from typing import Optional, cast
from unittest.mock import create_autospec

from scaler.config.types.address import AddressConfig
from scaler.io.mixins import AsyncBinder, AsyncConnector, AsyncObjectStorageConnector
from scaler.protocol.capnp import ProcessorInitialized, Task, TaskResult, TaskResultType
from scaler.utility.identifiers import ClientID, ObjectID, ProcessorID, TaskID, WorkerID
from scaler.utility.logging.utility import setup_logger
from scaler.utility.metadata.profile_result import ProfileResult
from scaler.utility.metadata.task_flags import TaskFlags
from scaler.worker.agent.mixins import HeartbeatManager, ProfilingManager
from scaler.worker.agent.processor_manager import VanillaProcessorManager
from scaler.worker.agent.task_manager import VanillaTaskManager
from tests.utility.utility import logging_test_name

CLIENT_ID = ClientID(b"client-under-test")
WORKER_ID = WorkerID(b"worker-under-test")
FUNCTION_OBJECT_ID = ObjectID(b"function-object-id-padded-to-32b")

INTERNAL_ADDRESS = AddressConfig.from_string("tcp://127.0.0.1:5555")
SCHEDULER_ADDRESS = AddressConfig.from_string("tcp://127.0.0.1:5556")

LOW_TASK_PRIORITY = 0
HIGH_TASK_PRIORITY = 1

TASK_TIMEOUT_SECONDS = 60
GARBAGE_COLLECT_INTERVAL_SECONDS = 1
TRIM_MEMORY_THRESHOLD_BYTES = 0

ROUTINE_TIMEOUT_SECONDS = 5

FIRST_PROCESSOR_PID = 1001
SECOND_PROCESSOR_PID = 1002

KILLED_BY_SIGKILL = -9


def make_task(priority: int) -> Task:
    return Task(
        taskId=TaskID.generate_task_id(),
        source=CLIENT_ID,
        metadata=TaskFlags(priority=priority).serialize(),
        funcObjectId=FUNCTION_OBJECT_ID,
        functionArgs=[],
        capabilities=[],
    )


class StubProcessorHolder:
    """Mirrors the ``ProcessorHolder`` contract without spawning a process.

    ``resume()`` keeps the real holder's precondition (it dereferences the holder's task) and reports the
    death of a processor that was killed while suspended.
    """

    def __init__(self, pid: int):
        self._pid = pid
        self._processor_id: Optional[ProcessorID] = None
        self._task: Optional[Task] = None
        self._suspended = False
        self._alive = True

    def pid(self) -> int:
        return self._pid

    def exitcode(self) -> Optional[int]:
        return None if self._alive else KILLED_BY_SIGKILL

    def processor_id(self) -> ProcessorID:
        assert self._processor_id is not None
        return self._processor_id

    def initialized(self) -> bool:
        return self._processor_id is not None

    def initialize(self, processor_id: ProcessorID) -> None:
        self._processor_id = processor_id

    def task(self) -> Optional[Task]:
        return self._task

    def set_task(self, task: Optional[Task]) -> None:
        self._task = task

    def suspended(self) -> bool:
        return self._suspended

    def suspend(self) -> None:
        assert self._task is not None
        assert self._suspended is False
        self._suspended = True

    def resume(self) -> bool:
        assert self._task is not None
        assert self._suspended is True

        if not self._alive:
            return False

        self._suspended = False
        return True

    def kill(self) -> None:
        self._alive = False

    def die(self) -> None:
        """The processor is killed from the outside, for example by the operating system's OOM killer."""
        self._alive = False


class BlockingObjectStorageConnector:
    """Holds ``set_object()`` open so the test can run the task routine inside ``on_failing_processor``."""

    def __init__(self):
        self.set_object_entered = asyncio.Event()
        self.set_object_may_return = asyncio.Event()

    async def wait_until_connected(self) -> None:
        return None

    async def set_object(self, object_id: ObjectID, payload: bytes) -> None:
        self.set_object_entered.set()
        await self.set_object_may_return.wait()

    def destroy(self) -> None:
        return None


class TestSuspendedProcessorDeath(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        setup_logger()
        logging_test_name(self)

        self._holders = [StubProcessorHolder(FIRST_PROCESSOR_PID), StubProcessorHolder(SECOND_PROCESSOR_PID)]
        self._started_holders = 0

        self._storage = BlockingObjectStorageConnector()
        self._profiling_manager = create_autospec(ProfilingManager, instance=True)
        self._profiling_manager.on_task_end.return_value = ProfileResult()

        heartbeat_manager = create_autospec(HeartbeatManager, instance=True)
        heartbeat_manager.get_object_storage_address.return_value = SCHEDULER_ADDRESS

        self._processor_manager = VanillaProcessorManager(
            identity=WORKER_ID,
            event_loop="builtin",
            address_internal=INTERNAL_ADDRESS,
            scheduler_address=SCHEDULER_ADDRESS,
            preload=None,
            garbage_collect_interval_seconds=GARBAGE_COLLECT_INTERVAL_SECONDS,
            trim_memory_threshold_bytes=TRIM_MEMORY_THRESHOLD_BYTES,
            hard_processor_suspend=False,
            logging_paths=(),
            logging_level="ERROR",
        )
        self._task_manager = VanillaTaskManager(task_timeout_seconds=TASK_TIMEOUT_SECONDS)

        self._processor_manager.register(
            heartbeat_manager=heartbeat_manager,
            task_manager=self._task_manager,
            profiling_manager=self._profiling_manager,
            connector_external=create_autospec(AsyncConnector, instance=True),
            binder_internal=create_autospec(AsyncBinder, instance=True),
            connector_storage=cast(AsyncObjectStorageConnector, self._storage),
        )
        self._task_manager.register(create_autospec(AsyncConnector, instance=True), self._processor_manager)

        patcher = unittest.mock.patch(
            "scaler.worker.agent.processor_manager.ProcessorHolder", side_effect=self.__next_stub_holder
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def __next_stub_holder(self, *args, **kwargs) -> StubProcessorHolder:
        holder = self._holders[self._started_holders]
        self._started_holders += 1
        return holder

    async def __initialize_current_processor(self) -> None:
        await self._processor_manager.on_processor_initialized(
            ProcessorID.generate_processor_id(), ProcessorInitialized()
        )

    async def test_worker_stays_available_when_a_suspended_processor_dies(self) -> None:
        """A suspended processor dying must not close the accept-task lock for good.

        The task routine and ``on_failing_processor`` both reach for the suspended task. Whichever way they
        interleave, the worker has to end up either running something or able to accept something.
        """

        await self._processor_manager.initialize()
        await self.__initialize_current_processor()

        # the low priority task starts on the first processor
        low_priority_task = make_task(LOW_TASK_PRIORITY)
        await self._task_manager.on_task_new(low_priority_task)
        await asyncio.wait_for(self._task_manager.routine(), timeout=ROUTINE_TIMEOUT_SECONDS)
        self.assertEqual(self._processor_manager.current_task_id(), low_priority_task.taskId)

        # the high priority task suspends it and starts on a second processor
        high_priority_task = make_task(HIGH_TASK_PRIORITY)
        await self._task_manager.on_task_new(high_priority_task)
        self.assertEqual(self._processor_manager.num_suspended_processors(), 1)
        await self.__initialize_current_processor()
        await asyncio.wait_for(self._task_manager.routine(), timeout=ROUTINE_TIMEOUT_SECONDS)
        self.assertEqual(self._processor_manager.current_task_id(), high_priority_task.taskId)

        suspended_holder, running_holder = self._holders

        # the task routine parks on the accept-task lock, which the running processor still holds
        routine = asyncio.create_task(self._task_manager.routine())
        await asyncio.sleep(0)
        self.assertFalse(routine.done())

        # the suspended processor is killed and the heartbeat reports it
        suspended_holder.die()
        failing = asyncio.create_task(
            self._processor_manager.on_failing_processor(suspended_holder.processor_id(), "zombie")
        )
        await asyncio.wait_for(self._storage.set_object_entered.wait(), timeout=ROUTINE_TIMEOUT_SECONDS)

        # the running processor finishes, which hands the accept-task lock to the parked routine
        await self._processor_manager.on_task_result(
            running_holder.processor_id(),
            TaskResult(taskId=high_priority_task.taskId, resultType=TaskResultType.success, metadata=b"", results=[]),
        )
        await asyncio.wait_for(routine, timeout=ROUTINE_TIMEOUT_SECONDS)

        self._storage.set_object_may_return.set()
        await asyncio.wait_for(failing, timeout=ROUTINE_TIMEOUT_SECONDS)

        self.assertIsNone(self._processor_manager.current_task(), "no processor should be running a task")
        self.assertTrue(
            self._processor_manager.can_accept_task(),
            "worker holds the accept-task lock while no processor is running a task, so it can never take work again",
        )

        # and it really can take work again
        next_task = make_task(LOW_TASK_PRIORITY)
        await self._task_manager.on_task_new(next_task)
        await asyncio.wait_for(self._task_manager.routine(), timeout=ROUTINE_TIMEOUT_SECONDS)
        self.assertEqual(self._processor_manager.current_task_id(), next_task.taskId)


if __name__ == "__main__":
    unittest.main()
