from typing import List, Tuple

from scaler.protocol.capnp import TaskState

TERMINAL_TASK_STATES = (
    TaskState.success,
    TaskState.failed,
    TaskState.failedWorkerDied,
    TaskState.canceled,
    TaskState.canceledNotFound,
)


class TaskStateMachine:
    """Records the state of one task.

    The machine holds no transition table. Legality lives in the action that handles an event: an action answers every
    source state and returns the state that the task lands in, or ``None`` when the event is not permitted. See
    ``VanillaTaskController.__route``.
    """

    def __init__(self, debug: bool):
        self._debug = debug
        self._paths: List[Tuple[TaskState, str]] = list()

        self._state: TaskState = TaskState.inactive

    def __repr__(self) -> str:
        return f"TaskStateMachine(state={self._state.name})"

    def get_path(self) -> str:
        return (
            " ".join(f"[{state.name}] -{event_name}->" for state, event_name in self._paths) + f" [{self._state.name}]"
        )

    def current_state(self) -> TaskState:
        return self._state

    def commit(self, event_name: str, target: TaskState) -> None:
        if self._debug:
            self._paths.append((self._state, event_name))

        self._state = target
