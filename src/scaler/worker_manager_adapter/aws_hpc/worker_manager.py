from __future__ import annotations

import asyncio
import logging
import math
from typing import TYPE_CHECKING, List, Optional

from scaler.config.section.aws_hpc_worker_manager import AWSBatchWorkerManagerConfig, AWSHPCBackend
from scaler.worker_manager_adapter.aws_hpc.worker import create_aws_batch_worker
from scaler.worker_manager_adapter.common import extract_desired_count
from scaler.worker_manager_adapter.mixins import DeclarativeWorkerProvisioner
from scaler.worker_manager_adapter.worker_manager_runner import WorkerManagerRunner
from scaler.worker_manager_adapter.worker_process import WorkerProcess

if TYPE_CHECKING:
    from scaler.protocol.capnp import WorkerManagerCommand


class BatchWorkerProvisioner(DeclarativeWorkerProvisioner):
    def __init__(self, config: AWSBatchWorkerManagerConfig) -> None:
        self._config = config
        self._base_concurrency = config.max_concurrent_jobs
        self._capabilities = config.worker_config.per_worker_capabilities.capabilities
        self._units: List[WorkerProcess] = []
        self._desired_count: int = 0
        self._reconcile_lock: asyncio.Lock = asyncio.Lock()
        self._pending_reconcile_task: Optional[asyncio.Task] = None
        self._active_reconcile_task: Optional[asyncio.Task] = None

    async def set_desired_task_concurrency(
        self, requests: List[WorkerManagerCommand.DesiredTaskConcurrencyRequest]
    ) -> None:
        task_concurrency = extract_desired_count(requests, self._capabilities)
        new_desired = math.ceil(task_concurrency / self._base_concurrency) if task_concurrency > 0 else 0
        if new_desired != self._desired_count:
            logging.info(
                f"Desired worker process count changed: {self._desired_count} → {new_desired} "
                f"(task_concurrency={task_concurrency}, base_concurrency={self._base_concurrency})"
            )
        self._desired_count = new_desired
        if self._pending_reconcile_task is None:
            self._pending_reconcile_task = asyncio.create_task(self._reconcile())

    async def _reconcile(self) -> None:
        async with self._reconcile_lock:
            self._active_reconcile_task = asyncio.current_task()
            self._pending_reconcile_task = None
            try:
                current = len(self._units)
                delta = self._desired_count - current
                msg = f"Reconcile: desired={self._desired_count}, current={current}, delta={delta:+d}"
                if delta != 0:
                    logging.info(msg)
                else:
                    logging.debug(msg)
                if delta > 0:
                    await self.start_units(delta)
                elif delta < 0:
                    await self.stop_units(abs(delta))
            except Exception as exc:
                logging.exception(f"Reconcile failed: {exc}")
            finally:
                self._active_reconcile_task = None

    async def start_units(self, count: int) -> None:
        config = self._config
        for _ in range(count):
            worker = create_aws_batch_worker(
                name=config.name,
                address=config.worker_manager_config.effective_worker_scheduler_address,
                object_storage_address=config.worker_manager_config.object_storage_address,
                job_queue=config.job_queue,
                job_definition=config.job_definition,
                aws_region=config.aws_region,
                s3_bucket=config.s3_bucket,
                s3_prefix=config.s3_prefix,
                capabilities=self._capabilities,
                base_concurrency=self._base_concurrency,
                heartbeat_interval_seconds=config.worker_config.heartbeat_interval_seconds,
                death_timeout_seconds=config.worker_config.death_timeout_seconds,
                task_queue_size=config.worker_config.per_worker_task_queue_size,
                io_threads=config.worker_config.io_threads,
                event_loop=config.worker_config.event_loop,
                job_timeout_seconds=config.job_timeout_minutes * 60,
                worker_manager_id=config.worker_manager_config.worker_manager_id.encode(),
            )
            worker.start()
            self._units.append(worker)
            logging.info(f"Started Batch worker process {worker.name!r}")

    async def stop_units(self, count: int) -> None:
        to_stop = self._units[:count]
        if len(to_stop) < count:
            logging.warning(f"Requested to stop {count} worker process(es) but only {len(to_stop)} available.")
        del self._units[:count]
        for worker in to_stop:
            worker.terminate()
            worker.join()
            logging.info(f"Stopped Batch worker process {worker.name!r}")

    def terminate_all(self) -> None:
        for worker in self._units:
            worker.terminate()
            worker.join()
        self._units.clear()


class AWSHPCWorkerManager:
    def __init__(self, config: AWSBatchWorkerManagerConfig) -> None:
        self._config = config

    def run(self) -> None:
        config = self._config
        logging.info(f"Starting AWS HPC Worker Manager (backend: {config.backend.name})")
        if config.backend != AWSHPCBackend.batch:
            raise NotImplementedError(f"backend {config.backend.name!r} is not yet implemented")

        provisioner = BatchWorkerProvisioner(config)
        runner = WorkerManagerRunner(
            address=config.worker_manager_config.scheduler_address,
            name="worker_manager_aws_hpc",
            heartbeat_interval_seconds=config.worker_config.heartbeat_interval_seconds,
            capabilities=config.worker_config.per_worker_capabilities.capabilities,
            max_provisioner_units=-1,
            worker_manager_id=config.worker_manager_config.worker_manager_id.encode(),
            worker_provisioner=provisioner,
            io_threads=config.worker_config.io_threads,
            workers_per_provisioner_unit=config.max_concurrent_jobs,
        )
        try:
            runner.run()
        finally:
            provisioner.terminate_all()
