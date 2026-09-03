"""Routing of Symphony task responses back to the futures that are waiting on them.

Holds no ``soamapi`` values, only annotations, so it is importable and unit testable without a Symphony
installation. Keeping it out of ``callback`` lets ``_soam.session_callback`` depend on it without the two
modules importing each other.
"""

from __future__ import annotations

import concurrent.futures
import threading
from typing import TYPE_CHECKING, Callable, Dict

import cloudpickle

if TYPE_CHECKING:
    import soamapi

    from scaler.worker_manager.proxy.symphony._soam.message import SoamMessage


class TaskResponseRouter:
    """Tracks in-flight Symphony tasks and completes their futures as responses arrive.

    Holds no ``soamapi`` values, so it stays usable without a Symphony installation. Its methods are
    called from threads owned by the Symphony API, so access to the future map is locked.
    """

    def __init__(self, message_factory: Callable[[], SoamMessage]) -> None:
        self._message_factory = message_factory
        self._callback_lock = threading.Lock()
        self._task_id_to_future: Dict[str, concurrent.futures.Future] = {}

    def on_response(self, task_output_handle: soamapi.TaskOutputHandle) -> None:
        with self._callback_lock:
            task_id = task_output_handle.get_id()

            future = self._task_id_to_future.pop(task_id)

            if task_output_handle.is_successful():
                output_message = self._message_factory()
                task_output_handle.populate_task_output(output_message)
                result = cloudpickle.loads(output_message.get_payload())
                future.set_result(result)
            else:
                # get_embedded_exception() returns None when Symphony itself failed the task rather
                # than the service raising, which makes set_exception() raise. Fixed separately.
                embedded_exception = task_output_handle.get_exception().get_embedded_exception()
                future.set_exception(embedded_exception)

    def on_exception(self, exception: soamapi.SoamException) -> None:
        with self._callback_lock:
            for future in self._task_id_to_future.values():
                future.set_exception(exception)

            self._task_id_to_future.clear()

    def submit_task(self, task_id: str, future: concurrent.futures.Future) -> None:
        self._task_id_to_future[task_id] = future

    def get_callback_lock(self) -> threading.Lock:
        return self._callback_lock
