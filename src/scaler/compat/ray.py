"""
This module provides a compatibility layer for Scaler that mimics the Ray interface.
It allows users familiar with Ray's API to interact with Scaler in a similar fashion,
including remote function execution, object referencing, and waiting for task completion.
"""

import concurrent.futures
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
    *,
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
    """
    Initializes a Scaler cluster. Mimics the behavior of `ray.init()`.

    If `address` is provided, it connects to an existing Scaler cluster.
    Otherwise, it starts a new local cluster with the specified configuration.

    Args:
        address: The address of the Scaler scheduler to connect to.
        n_workers: The number of workers to start in the local cluster.
            Defaults to the number of CPU cores.
        **kwargs: Other Scaler cluster configuration options.
    """
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
    """
    Disconnects the client and shuts down the local cluster if one was created.

    Mimics the behavior of `ray.shutdown()`.
    """
    global client, combo

    if client:
        client.disconnect()
    if combo:
        combo.shutdown()

    client = None
    combo = None


def is_initialized() -> bool:
    """Checks if the Scaler client has been initialized."""
    return client is not None


def ensure_init():
    """
    This is an internal function that ensures the Scaler client is initialized, calling `init()` with
    default parameters if it is not.
    """
    if not is_initialized():
        init()


T = TypeVar("T")
P = ParamSpec("P")


class RayObjectReference(Generic[T]):
    """
    A wrapper around a ScalerFuture to provide an API similar to a Ray ObjectRef.

    This class allows treating results of asynchronous Scaler tasks in a way
    that is compatible with the Ray API.
    """

    _future: ScalerFuture

    def __init__(self, future: ScalerFuture) -> None:
        """
        Initializes the RayObjectReference with a ScalerFuture.

        Args:
            future: The ScalerFuture instance to wrap.
        """
        self._future = future

    def get(self) -> T:
        """
        Retrieves the result of the future, blocking until it's available.

        Returns:
            The result of the completed future.
        """
        return self._future.result()

    def cancel(self) -> None:
        """Attempts to cancel the future."""
        self._future.cancel()


def unwrap_ray_object_reference(maybe_ref: Union[T, RayObjectReference[T]]) -> T:
    """
    Helper to get the result if the input is a RayObjectReference.

    If the input is a `RayObjectReference`, its result is returned.
    Otherwise, the input is returned as is. This is used to transparently
    handle passing of object references as arguments to remote functions.

    Args:
        maybe_ref: The object to unwrap.

    Returns:
        The result of the reference or the original object.
    """
    if isinstance(maybe_ref, RayObjectReference):
        return maybe_ref.get()
    return maybe_ref


class RayRemote(Generic[P, T]):
    """
    A wrapper for a function to make it "remote," similar to a Ray remote function.

    This class is typically instantiated by the `@ray.remote` decorator.
    """

    _fn: Callable[Concatenate[Client, P], T]

    def __init__(self, fn: Callable[P, T]) -> None:
        """
        Initializes the remote function wrapper.

        Args:
            fn: The Python function to be executed remotely.
        """
        # this function forwards the implicit client to the worker and enables nesting
        def forward_client(client: Client, *args: P.args, **kwargs: P.kwargs) -> T:
            from scaler.compat import ray

            ray.client = client
            return fn(*args, **kwargs)

        self._fn = forward_client

    def remote(self, *args: P.args, **kwargs: P.kwargs) -> RayObjectReference:
        """
        Executes the wrapped function remotely.

        Args:
            *args: Positional arguments for the remote function.
            **kwargs: Keyword arguments for the remote function.

        Returns:
            A RayObjectReference that can be used to retrieve the result.
        """
        if not is_initialized():
            raise RuntimeError("Scaler is not initialized")

        # Ray supports passing object references into other remote functions
        # so we must take special care to get their values
        args = [unwrap_ray_object_reference(arg) for arg in args]
        kwargs = {k: unwrap_ray_object_reference(v) for k, v in kwargs.items()}

        future = client.submit(self._fn, client, *args, **kwargs)
        return RayObjectReference(future)


def get(ref: Union[RayObjectReference[T], List[RayObjectReference[Any]]]) -> Union[T, List[Any]]:
    """
    Retrieves the result from one or more RayObjectReferences.

    This function blocks until the results are available. Mimics `ray.get()`.

    Args:
        ref: A single RayObjectReference or a list of them.

    Returns:
        The result of the reference or a list of results.
    """
    if isinstance(ref, List):
        return [get(x) for x in ref]
    if isinstance(ref, RayObjectReference):
        return ref.get()
    raise RuntimeError(f"Unknown type [{type(ref)}] passed to ray.get()")


def put(obj: Any) -> ObjectReference:
    """
    Stores an object in the Scaler object store. Mimics `ray.put()`.

    Args:
        obj: The Python object to be stored.

    Returns:
        An ObjectReference that can be used to retrieve the object.
    """
    ensure_init()

    return client.send_object(obj)


def remote(fn, *_args, **_kwargs) -> RayRemote:
    """
    A decorator that creates a `RayRemote` instance from a regular function.

    Mimics the behavior of `@ray.remote`.

    Args:
        fn: The function to be converted into a remote function.

    Returns:
        A RayRemote instance that can be called with `.remote()`.
    """
    ensure_init()

    return RayRemote(fn)


def cancel(ref: RayObjectReference) -> None:
    """
    Attempts to cancel the execution of a task. Mimics `ray.cancel()`.

    Args:
        ref: The RayObjectReference corresponding to the task to be canceled.
    """
    ref.cancel()


def wait(
    refs: List[RayObjectReference], *, num_returns: Optional[int] = 1, timeout: Optional[float] = None
) -> Tuple[List[RayObjectReference], List[RayObjectReference]]:
    """
    Waits for a number of object references to be ready. Mimics `ray.wait()`.

    Args:
        refs: A list of RayObjectReferences to wait on.
        num_returns: The number of references to wait for. If None, waits for all.
        timeout: The maximum time in seconds to wait.

    Returns:
        A tuple containing two lists: the list of ready references and the
        list of remaining, not-ready references.
    """

    if num_returns is not None and num_returns > len(refs):
        raise ValueError("num_returns cannot be greater than the number of provided object references")

    if num_returns is not None and num_returns <= 0:
        return [], list(refs)

    future_to_ref = {ref._future: ref for ref in refs}
    done = set()

    try:
        for future in concurrent.futures.as_completed((ref._future for ref in refs), timeout=timeout):
            done.add(future_to_ref[future])

            if num_returns is not None and len(done) == num_returns:
                break
    except concurrent.futures.TimeoutError:
        pass

    return list(done), [ref for ref in refs if ref not in done]
