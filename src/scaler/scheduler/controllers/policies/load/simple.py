from typing import Dict, List, Optional, Set

from scaler.protocol.python.message import InformationSnapshot, Task
from scaler.scheduler.controllers.policies.allocation.mixins import TaskAllocatePolicy
from scaler.scheduler.controllers.policies.load.mixins import LoadPolicy
from scaler.scheduler.controllers.policies.scaling.mixins import ScalingController
from scaler.utility.identifiers import TaskID, WorkerID


class SimpleLoadPolicy(LoadPolicy):
    def __init__(self, allocation_policy: TaskAllocatePolicy, scaling_policy: ScalingController):
        self._allocation_policy = allocation_policy
        self._scaling_policy = scaling_policy

    def add_worker(self, worker: WorkerID, capabilities: Dict[str, int], queue_size: int) -> bool:
        return self._allocation_policy.add_worker(worker, capabilities, queue_size)

    def remove_worker(self, worker: WorkerID) -> List[TaskID]:
        return self._allocation_policy.remove_worker(worker)

    def get_worker_ids(self) -> Set[WorkerID]:
        return self._allocation_policy.get_worker_ids()

    def get_worker_by_task_id(self, task_id: TaskID) -> WorkerID:
        return self._allocation_policy.get_worker_by_task_id(task_id)

    def balance(self) -> Dict[WorkerID, List[TaskID]]:
        return self._allocation_policy.balance()

    def assign_task(self, task: Task) -> WorkerID:
        return self._allocation_policy.assign_task(task)

    def remove_task(self, task_id: TaskID) -> WorkerID:
        return self._allocation_policy.remove_task(task_id)

    def has_available_worker(self, capabilities: Optional[Dict[str, int]] = None) -> bool:
        return self._allocation_policy.has_available_worker(capabilities)

    def statistics(self) -> Dict:
        return self._allocation_policy.statistics()

    async def on_snapshot(self, snapshot: InformationSnapshot):
        await self._scaling_policy.on_snapshot(snapshot)

    def get_status(self):
        return self._scaling_policy.get_status()
