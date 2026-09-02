import asyncio
import logging
from concurrent.futures import Future
from typing import Any, List, Tuple

import cloudpickle

from scaler.protocol.capnp import Task, TaskCancel
from scaler.utility.identifiers import TaskID
from scaler.worker_manager.proxy.mixins import ExecutionBackend, TaskDeserializer, TaskInputLoader
from scaler.worker_manager.proxy.symphony.callback import TaskResponseRouter, create_session_callback_class
from scaler.worker_manager.proxy.symphony.message import create_soam_message_class
from scaler.worker_manager.proxy.symphony.soam_api import load_soam_api

logger = logging.getLogger(__name__)


class SymphonyExecutionBackend(TaskInputLoader, ExecutionBackend):
    _loader: TaskDeserializer

    def __init__(self, service_name: str):
        self._service_name = service_name

        self._soam_api = load_soam_api()
        self._soam_api.initialize()

        self._message_class = create_soam_message_class()
        self._response_router = TaskResponseRouter(self._message_class)
        self._session_callback = create_session_callback_class()(self._response_router)

        self._ibm_soam_connection = self._soam_api.connect(
            self._service_name, self._soam_api.DefaultSecurityCallback("Guest", "Guest")
        )
        logger.info(f"established IBM Spectrum Symphony connection {self._ibm_soam_connection.get_id()}")

        ibm_soam_session_attr = self._soam_api.SessionCreationAttributes()
        ibm_soam_session_attr.set_session_type("RecoverableAllHistoricalData")
        ibm_soam_session_attr.set_session_name("ScalerSession")
        ibm_soam_session_attr.set_session_flags(self._soam_api.SessionFlags.PARTIAL_ASYNC)
        ibm_soam_session_attr.set_session_callback(self._session_callback)
        self._ibm_soam_session = self._ibm_soam_connection.create_session(ibm_soam_session_attr)
        logger.info(f"established IBM Spectrum Symphony session {self._ibm_soam_session.get_id()}")

    def register(self, load_task_inputs: TaskDeserializer) -> None:
        self._loader = load_task_inputs

    async def load_task_inputs(self, task: Task) -> Tuple[Any, List[Any]]:
        return await self._loader(task)

    async def on_cancel(self, task_cancel: TaskCancel) -> None:
        pass

    def on_cleanup(self, task_id: TaskID) -> None:
        pass

    async def routine(self) -> None:
        pass

    async def execute(self, task: Task) -> asyncio.Future:
        function, arg_objects = await self.load_task_inputs(task)

        input_message = self._message_class()
        input_message.set_payload(cloudpickle.dumps((function, *arg_objects)))

        task_attr = self._soam_api.TaskSubmissionAttributes()
        task_attr.set_task_input(input_message)

        with self._response_router.get_callback_lock():
            symphony_task = self._ibm_soam_session.send_task_input(task_attr)

            future: Future = Future()
            future.set_running_or_notify_cancel()

            self._response_router.submit_task(symphony_task.get_id(), future)

        return asyncio.wrap_future(future)
