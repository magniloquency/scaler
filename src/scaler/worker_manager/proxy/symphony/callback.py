import concurrent.futures
import functools
import threading
from typing import Any, Callable, Dict, Type

import cloudpickle

from scaler.worker_manager.proxy.symphony.soam_api import load_soam_api


class TaskResponseRouter:
    """Tracks in-flight Symphony tasks and completes their futures as responses arrive.

    Holds no ``soamapi`` types, so it stays usable without a Symphony installation. Its methods are
    called from threads owned by the Symphony API, so access to the future map is locked.
    """

    def __init__(self, message_factory: Callable[[], Any]):
        self._message_factory = message_factory
        self._callback_lock = threading.Lock()
        self._task_id_to_future: Dict[str, concurrent.futures.Future] = {}

    def on_response(self, task_output_handle) -> None:
        with self._callback_lock:
            task_id = task_output_handle.get_id()

            future = self._task_id_to_future.pop(task_id)

            if task_output_handle.is_successful():
                output_message = self._message_factory()
                task_output_handle.populate_task_output(output_message)
                result = cloudpickle.loads(output_message.get_payload())
                future.set_result(result)
            else:
                future.set_exception(task_output_handle.get_exception().get_embedded_exception())

    def on_exception(self, exception) -> None:
        with self._callback_lock:
            for future in self._task_id_to_future.values():
                future.set_exception(exception)

            self._task_id_to_future.clear()

    def submit_task(self, task_id: str, future: concurrent.futures.Future) -> None:
        self._task_id_to_future[task_id] = future

    def get_callback_lock(self) -> threading.Lock:
        return self._callback_lock


@functools.lru_cache(maxsize=1)
def create_session_callback_class() -> Type[Any]:
    """Build the ``soamapi.SessionCallback`` subclass that forwards events to a ``TaskResponseRouter``.

    The class is built on demand because its base class only exists once ``soamapi`` is importable.
    """
    soam_api = load_soam_api()

    # mypy cannot resolve a base class that is only available at run time
    class SessionCallback(soam_api.SessionCallback):  # type: ignore[name-defined]
        def __init__(self, response_router: TaskResponseRouter):
            self._response_router = response_router

        def on_response(self, task_output_handle):
            self._response_router.on_response(task_output_handle)

        def on_exception(self, exception):
            self._response_router.on_exception(exception)

    return SessionCallback
