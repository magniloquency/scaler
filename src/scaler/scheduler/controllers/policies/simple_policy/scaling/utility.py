from typing import Dict, Optional

from scaler.scheduler.controllers.policies.simple_policy.scaling.capability_scaling import CapabilityScalingPolicy
from scaler.scheduler.controllers.policies.simple_policy.scaling.mixins import ScalingPolicy
from scaler.scheduler.controllers.policies.simple_policy.scaling.static import StaticScalingPolicy
from scaler.scheduler.controllers.policies.simple_policy.scaling.types import ScalingPolicyStrategy, WorkerManagerBounds
from scaler.scheduler.controllers.policies.simple_policy.scaling.vanilla import VanillaScalingPolicy


def create_scaling_policy(scaling: str) -> ScalingPolicy:
    """Build a scaling policy from its `name[:argument]` string, or `name[entries]`.

    Only `static` takes an argument, and only `static` and `vanilla` take entries:

        static                          every worker manager runs its advertised maximum
        static:4                        every worker manager runs 4, capped at its advertised maximum
        static[native:4, ecs:0]         native runs 4, ecs runs 0, any other runs its advertised maximum
        vanilla                         every worker manager scales between 0 and its advertised maximum
        vanilla[native:8:8, ecs:100]    native holds 8, ecs scales between 0 and 100
        capability                      scales per capability group

    An argument and entries cannot be combined: `static:2[native:4]` is refused."""
    # `name[entries]`: the entries are everything between the first `[` and the closing `]`.
    name, bracket, entries = scaling.partition("[")
    if bracket:
        scaling_policy_strategy = ScalingPolicyStrategy(name)
        if not entries.endswith("]"):
            raise ValueError(f"{name} entries must end with ']', got {scaling!r}")
        if scaling_policy_strategy == ScalingPolicyStrategy.STATIC:
            return StaticScalingPolicy(None, _parse_static_task_concurrencies(entries[:-1]))
        if scaling_policy_strategy == ScalingPolicyStrategy.VANILLA:
            return VanillaScalingPolicy(_parse_vanilla_bounds(entries[:-1]))
        raise ValueError(f"only the static and vanilla scaling policies take entries, got {scaling!r}")

    # `name[:argument]`: an empty argument means none was given.
    name, _, argument = scaling.partition(":")
    scaling_policy_strategy = ScalingPolicyStrategy(name)

    if scaling_policy_strategy == ScalingPolicyStrategy.STATIC:
        return StaticScalingPolicy(_parse_static_task_concurrency(argument), {})

    # Every other policy is a bare name.
    if argument:
        raise ValueError(f"scaling policy {name!r} takes no argument, got {scaling!r}")

    if scaling_policy_strategy == ScalingPolicyStrategy.VANILLA:
        return VanillaScalingPolicy({})
    elif scaling_policy_strategy == ScalingPolicyStrategy.CAPABILITY:
        return CapabilityScalingPolicy()

    raise ValueError(f"unsupported scaling policy strategy: {scaling_policy_strategy}")


def _parse_static_task_concurrency(argument: str) -> Optional[int]:
    if not argument:
        return None

    if not argument.isdigit():
        raise ValueError(f"static scaling takes a non-negative task concurrency, got {argument!r}")

    return int(argument)


def _parse_static_task_concurrencies(text: str) -> Dict[bytes, int]:
    """Parse `worker_manager_id:task_concurrency` entries separated by `,`."""
    task_concurrency_by_manager: Dict[bytes, int] = {}
    for entry in text.split(","):
        fields = [field.strip() for field in entry.split(":")]
        if len(fields) != 2 or not fields[0]:
            raise ValueError(f"static entry must be 'worker_manager_id:task_concurrency', got {entry.strip()!r}")

        worker_manager_id = fields[0].encode()
        if worker_manager_id in task_concurrency_by_manager:
            raise ValueError(f"static entries name worker manager {fields[0]!r} twice")

        task_concurrency_by_manager[worker_manager_id] = _parse_count(fields[1], entry)

    return task_concurrency_by_manager


def _parse_vanilla_bounds(text: str) -> Dict[bytes, WorkerManagerBounds]:
    """Parse `worker_manager_id:max_task_concurrency[:min_task_concurrency]` entries separated by `,`.

    An empty max_task_concurrency leaves the cap to the manager's advertised maximum."""
    bounds: Dict[bytes, WorkerManagerBounds] = {}
    for entry in text.split(","):
        fields = [field.strip() for field in entry.split(":")]
        if len(fields) not in (2, 3) or not fields[0]:
            raise ValueError(
                f"vanilla bounds entry must be 'worker_manager_id:max_task_concurrency[:min_task_concurrency]', "
                f"got {entry.strip()!r}"
            )

        worker_manager_id = fields[0].encode()
        if worker_manager_id in bounds:
            raise ValueError(f"vanilla bounds name worker manager {fields[0]!r} twice")

        max_task_concurrency = _parse_count(fields[1], entry) if fields[1] else None
        min_task_concurrency = _parse_count(fields[2], entry) if len(fields) == 3 else 0
        if max_task_concurrency is not None and min_task_concurrency > max_task_concurrency:
            raise ValueError(f"vanilla bounds entry {entry.strip()!r}: the minimum exceeds the maximum")

        bounds[worker_manager_id] = WorkerManagerBounds(max_task_concurrency, min_task_concurrency)

    return bounds


def _parse_count(field: str, entry: str) -> int:
    if not field.isdigit():
        raise ValueError(f"scaling entry {entry.strip()!r}: {field!r} is not a non-negative task concurrency")

    return int(field)
