from typing import Any, Callable, Dict, Generic, List, Optional, Tuple, TypeVar, Union

import psutil
from typing_extensions import Concatenate, ParamSpec

from scaler.client.client import Client
from scaler.client.future import ScalerFuture
from scaler.client.object_reference import ObjectReference
from scaler.cluster.combo import SchedulerClusterCombo
from scaler.config.defaults import (
    DEFAULT_CLIENT_TIMEOUT_SECONDS,
    DEFAULT_GARBAGE_COLLECT_INTERVAL_SECONDS,
    DEFAULT_HARD_PROCESSOR_SUSPEND,
    DEFAULT_HEARTBEAT_INTERVAL_SECONDS,
    DEFAULT_IO_THREADS,
    DEFAULT_LOAD_BALANCE_SECONDS,
    DEFAULT_LOAD_BALANCE_TRIGGER_TIMES,
    DEFAULT_LOGGING_LEVEL,
    DEFAULT_LOGGING_PATHS,
    DEFAULT_MAX_NUMBER_OF_TASKS_WAITING,
    DEFAULT_OBJECT_RETENTION_SECONDS,
    DEFAULT_PER_WORKER_QUEUE_SIZE,
    DEFAULT_TASK_TIMEOUT_SECONDS,
    DEFAULT_TRIM_MEMORY_THRESHOLD_BYTES,
    DEFAULT_WORKER_DEATH_TIMEOUT,
    DEFAULT_WORKER_TIMEOUT_SECONDS,
)
from scaler.scheduler.allocate_policy.allocate_policy import AllocatePolicy

combo: Optional[SchedulerClusterCombo] = None
client: Optional[Client] = None


def init(
    address: Optional[str] = None,
    /,
    n_workers: Optional[int] = psutil.cpu_count(),
    object_storage_address: Optional[str] = None,
    monitor_address: Optional[str] = None,
    per_worker_capabilities: Optional[Dict[str, int]] = None,
    worker_io_threads: int = DEFAULT_IO_THREADS,
    scheduler_io_threads: int = DEFAULT_IO_THREADS,
    max_number_of_tasks_waiting: int = DEFAULT_MAX_NUMBER_OF_TASKS_WAITING,
    heartbeat_interval_seconds: int = DEFAULT_HEARTBEAT_INTERVAL_SECONDS,
    client_timeout_seconds: int = DEFAULT_CLIENT_TIMEOUT_SECONDS,
    worker_timeout_seconds: int = DEFAULT_WORKER_TIMEOUT_SECONDS,
    object_retention_seconds: int = DEFAULT_OBJECT_RETENTION_SECONDS,
    task_timeout_seconds: int = DEFAULT_TASK_TIMEOUT_SECONDS,
    death_timeout_seconds: int = DEFAULT_WORKER_DEATH_TIMEOUT,
    load_balance_seconds: int = DEFAULT_LOAD_BALANCE_SECONDS,
    load_balance_trigger_times: int = DEFAULT_LOAD_BALANCE_TRIGGER_TIMES,
    garbage_collect_interval_seconds: int = DEFAULT_GARBAGE_COLLECT_INTERVAL_SECONDS,
    trim_memory_threshold_bytes: int = DEFAULT_TRIM_MEMORY_THRESHOLD_BYTES,
    per_worker_task_queue_size: int = DEFAULT_PER_WORKER_QUEUE_SIZE,
    hard_processor_suspend: bool = DEFAULT_HARD_PROCESSOR_SUSPEND,
    protected: bool = True,
    allocate_policy: AllocatePolicy = AllocatePolicy.even,
    event_loop: str = "builtin",
    logging_paths: Tuple[str, ...] = DEFAULT_LOGGING_PATHS,
    logging_level: str = DEFAULT_LOGGING_LEVEL,
    logging_config_file: Optional[str] = None,
) -> None:
    global client, combo

    if client is not None:
        raise RuntimeError("Cannot initialize scaler twice")

    if address is None:
        combo = SchedulerClusterCombo(
            n_workers=n_workers,
            object_storage_address=object_storage_address,
            monitor_address=monitor_address,
            per_worker_capabilities=per_worker_capabilities,
            worker_io_threads=worker_io_threads,
            scheduler_io_threads=scheduler_io_threads,
            max_number_of_tasks_waiting=max_number_of_tasks_waiting,
            heartbeat_interval_seconds=heartbeat_interval_seconds,
            client_timeout_seconds=client_timeout_seconds,
            worker_timeout_seconds=worker_timeout_seconds,
            object_retention_seconds=object_retention_seconds,
            task_timeout_seconds=task_timeout_seconds,
            death_timeout_seconds=death_timeout_seconds,
            load_balance_seconds=load_balance_seconds,
            load_balance_trigger_times=load_balance_trigger_times,
            garbage_collect_interval_seconds=garbage_collect_interval_seconds,
            trim_memory_threshold_bytes=trim_memory_threshold_bytes,
            per_worker_task_queue_size=per_worker_task_queue_size,
            hard_processor_suspend=hard_processor_suspend,
            protected=protected,
            allocate_policy=allocate_policy,
            event_loop=event_loop,
            logging_paths=logging_paths,
            logging_level=logging_level,
            logging_config_file=logging_config_file,
        )
        client = Client(combo.get_address())
    else:
        client = Client(address=address)


def shutdown() -> None:
    global client, combo

    if client:
        client.disconnect()
    if combo:
        combo.shutdown()

    client = None
    combo = None


def is_initialized() -> bool:
    return client is not None


def ensure_init():
    if not is_initialized():
        init()


T = TypeVar("T")
P = ParamSpec("P")


class RayObjectReference(Generic[T]):
    _future: ScalerFuture

    def __init__(self, future: ScalerFuture) -> None:
        self._future = future


class RayRemote(Generic[P, T]):
    _fn: Callable[Concatenate[Client, P], T]

    def __init__(self, fn: Callable[P, T]) -> None:
        # this function forwards the implicit client to the worker and enables nesting
        def forward_client(client: Client, *args: P.args, **kwargs: P.kwargs) -> T:
            from scaler.compat import ray

            ray.client = client
            return fn(*args, **kwargs)

        self._fn = forward_client

    def remote(self, *args: P.args, **kwargs: P.kwargs) -> RayObjectReference:
        if not is_initialized():
            raise RuntimeError("Scaler is not initialized")

        future = client.submit(self._fn, client, *args, **kwargs)
        return RayObjectReference(future)


# there is practically no way to express that each element of the list can be a different generic type, so we use Any
def get(ref: Union[RayObjectReference[T], List[RayObjectReference[Any]]]) -> Union[T, List[Any]]:
    if isinstance(ref, List):
        return [get(x) for x in ref]
    if isinstance(ref, RayObjectReference):
        return ref._future.result()
    raise RuntimeError(f"Unknown type [{type(ref)}] passed to ray.get()")


def put(obj: Any) -> ObjectReference:
    ensure_init()

    return client.send_object(obj)


def remote(fn, *_args, **_kwargs) -> RayRemote:
    ensure_init()

    return RayRemote(fn)
