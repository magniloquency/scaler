from typing import Any, Callable, Generic, List, Optional, TypeVar, Union

import psutil
from typing_extensions import ParamSpec

from scaler.client.client import Client
from scaler.client.future import ScalerFuture
from scaler.client.object_reference import ObjectReference
from scaler.cluster.combo import SchedulerClusterCombo

combo: Optional[SchedulerClusterCombo] = None
client: Optional[Client] = None


def init(address: Optional[str] = None, n_workers: Optional[int] = psutil.cpu_count(), *_args, **_kwargs) -> None:
    global client, combo

    if client is not None:
        raise RuntimeError("Cannot initialize scaler twice")

    if address is None:
        combo = SchedulerClusterCombo(n_workers=n_workers)
        client = Client(combo.get_address())
    else:
        client = Client(address=address)


def shutdown() -> None:
    global client, combo

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
    _fn: Callable[P, T]

    def __init__(self, fn: Callable[P, T]) -> None:
        self._fn = fn

    def remote(self, *args: P.args, **kwargs: P.kwargs) -> RayObjectReference:
        future = client.submit(self._fn, *args, **kwargs)
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
