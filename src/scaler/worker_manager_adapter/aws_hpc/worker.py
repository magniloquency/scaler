"""
AWS HPC Worker.

Connects to the Scaler scheduler via ZMQ streaming and forwards tasks
to AWS Batch for execution via the TaskManager.
"""

from typing import Dict, List, Optional

from scaler.config.types.object_storage_server import ObjectStorageAddressConfig
from scaler.config.types.zmq import ZMQConfig
from scaler.utility.event_loop import create_async_loop_routine
from scaler.worker_manager_adapter.aws_hpc.heartbeat_manager import AWSBatchHeartbeatManager
from scaler.worker_manager_adapter.aws_hpc.task_manager import AWSHPCTaskManager
from scaler.worker_manager_adapter.base_heartbeat_manager import BaseHeartbeatManager
from scaler.worker_manager_adapter.base_task_manager import BaseTaskManager
from scaler.worker_manager_adapter.base_worker import BaseWorker


class AWSBatchWorker(BaseWorker):
    """
    AWS Batch Worker that receives tasks from the scheduler and submits them to AWS Batch.
    """

    def __init__(
        self,
        name: str,
        address: ZMQConfig,
        object_storage_address: Optional[ObjectStorageAddressConfig],
        job_queue: str,
        job_definition: str,
        aws_region: str,
        s3_bucket: str,
        worker_manager_id: bytes,
        s3_prefix: str = "scaler-tasks",
        capabilities: Optional[Dict[str, int]] = None,
        base_concurrency: int = 100,
        heartbeat_interval_seconds: int = 1,
        death_timeout_seconds: int = 30,
        task_queue_size: int = 1000,
        io_threads: int = 2,
        event_loop: str = "builtin",
        job_timeout_seconds: int = 3600,
    ) -> None:
        super().__init__(
            name=name,
            address=address,
            object_storage_address=object_storage_address,
            capabilities=capabilities or {},
            base_concurrency=base_concurrency,
            heartbeat_interval_seconds=heartbeat_interval_seconds,
            death_timeout_seconds=death_timeout_seconds,
            task_queue_size=task_queue_size,
            io_threads=io_threads,
            event_loop=event_loop,
            worker_manager_id=worker_manager_id,
        )
        self._job_queue = job_queue
        self._job_definition = job_definition
        self._aws_region = aws_region
        self._s3_bucket = s3_bucket
        self._s3_prefix = s3_prefix
        self._job_timeout_seconds = job_timeout_seconds

    def _create_heartbeat_manager(self) -> BaseHeartbeatManager:
        return AWSBatchHeartbeatManager(
            object_storage_address=self._object_storage_address,
            capabilities=self._capabilities,
            task_queue_size=self._task_queue_size,
            worker_manager_id=self._worker_manager_id,
        )

    def _create_task_manager(self) -> BaseTaskManager:
        return AWSHPCTaskManager(
            base_concurrency=self._base_concurrency,
            job_queue=self._job_queue,
            job_definition=self._job_definition,
            aws_region=self._aws_region,
            s3_bucket=self._s3_bucket,
            s3_prefix=self._s3_prefix,
            job_timeout_seconds=self._job_timeout_seconds,
        )

    def _get_extra_loops(self) -> List:
        return [create_async_loop_routine(self._task_manager.routine, 0)]
