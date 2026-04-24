from __future__ import annotations

from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

if TYPE_CHECKING:
    from scaler.protocol.capnp import WorkerManagerCommand


class CapacityExceededError(Exception):
    pass


class WorkerNotFoundError(Exception):
    pass


def extract_desired_count(
    requests: List[WorkerManagerCommand.DesiredTaskConcurrencyRequest], own_capabilities: Dict[str, int]
) -> Optional[int]:
    """Return the desired worker count for this provisioner from a declarative scaling command.

    Selects the most specific request whose capability set is a subset of own_capabilities.
    An empty capability set in a request acts as a wildcard that matches any provisioner.
    Returns None if no request matches.
    """
    best: Optional[Tuple[int, int]] = None  # (specificity, count)
    for request in requests:
        request_capabilities = {entry.key: entry.value for entry in request.capabilities}
        if request_capabilities.items() <= own_capabilities.items():
            specificity = len(request_capabilities)
            if best is None or specificity > best[0]:
                best = (specificity, request.taskConcurrency)
    return best[1] if best is not None else None


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
