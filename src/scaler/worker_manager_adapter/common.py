import asyncio
from typing import TYPE_CHECKING, Awaitable, Callable, Dict, List, Optional

if TYPE_CHECKING:
    from scaler.protocol.capnp import WorkerManagerCommand


async def reconcile(
    desired_count: int,
    units: List[str],
    start_unit: Callable[[], Awaitable[None]],
    stop_units: Callable[[List[str]], Awaitable[None]],
) -> None:
    """Converge the active unit set toward desired_count by calling start_unit or stop_units as needed."""
    delta = desired_count - len(units)
    if delta > 0:
        await asyncio.gather(*[start_unit() for _ in range(delta)], return_exceptions=True)
    elif delta < 0:
        await stop_units(units[: abs(delta)])


class CapacityExceededError(Exception):
    pass


class WorkerNotFoundError(Exception):
    pass


def extract_desired_count(
    requests: List["WorkerManagerCommand.DesiredTaskConcurrencyRequest"], own_capabilities: Dict[str, int]
) -> int:
    """Return the desired worker count for this provisioner from a declarative scaling command.

    Selects the most specific request whose capability set is a subset of own_capabilities.
    An empty capability set in a request acts as a wildcard that matches any provisioner.
    Returns 0 if no request matches.
    """
    best: Optional[tuple] = None  # (specificity, count)
    for request in requests:
        request_capabilities = {entry.key: entry.value for entry in request.capabilities}
        if request_capabilities.items() <= own_capabilities.items():
            specificity = len(request_capabilities)
            if best is None or specificity > best[0]:
                best = (specificity, request.taskConcurrency)
    return best[1] if best is not None else 0


def format_capabilities(capabilities: Dict[str, int]) -> str:
    """
    Reverse of `parse_capabilities`: convert a capabilities dict into a
    comma-separated capability string (e.g. "linux,cpu=4").
    Values equal to -1 are emitted as flag-style entries (no `=value`).
    """
    parts = []
    for name, value in capabilities.items():
        if value == -1:
            parts.append(name)
        else:
            parts.append(f"{name}={value}")
    return ",".join(parts)
