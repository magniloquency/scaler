from __future__ import annotations

import logging
import os
import signal
import sys
import uuid
from typing import Dict, Set

import psutil

from scaler.config.section.native_worker_manager import NativeWorkerManagerConfig
from scaler.utility.exitcode import describe_exitcode
from scaler.worker.worker import Worker
from scaler.worker_manager_adapter.unit_provisioner import UNLIMITED_UNITS, UnitProvisioner
from scaler.worker_manager_adapter.worker_manager_runner import WorkerManagerRunner

logger = logging.getLogger(__name__)

TASK_CONCURRENCY_PER_WORKER = 1
SENTINEL_POLL_INTERVAL_SECONDS = 1.0


class NativeWorkerProvisioner(UnitProvisioner):
    """A unit is one worker process on this machine.

    This is the only kind of manager that speaks to a worker, and it holds the only link to one.
    """

    def __init__(self, config: NativeWorkerManagerConfig) -> None:
        self._worker_scheduler_address = config.worker_manager_config.effective_worker_scheduler_address
        self._object_storage_address = config.worker_manager_config.object_storage_address
        self._capabilities = config.worker_config.per_worker_capabilities.capabilities
        self._worker_manager_id = config.worker_manager_config.worker_manager_id.encode()
        self._io_threads = config.worker_config.io_threads
        self._task_queue_size = config.worker_config.per_worker_task_queue_size
        self._max_task_concurrency = config.worker_manager_config.max_task_concurrency
        self._heartbeat_interval_seconds = config.worker_config.heartbeat_interval_seconds
        self._task_timeout_seconds = config.worker_config.task_timeout_seconds
        self._death_timeout_seconds = config.worker_config.death_timeout_seconds
        self._garbage_collect_interval_seconds = config.worker_config.garbage_collect_interval_seconds
        self._trim_memory_threshold_bytes = config.worker_config.trim_memory_threshold_bytes
        self._hard_processor_suspend = config.worker_config.hard_processor_suspend
        self._event_loop = config.worker_config.event_loop
        self._preload = config.worker_config.preload
        self._logging_paths = config.logging_config.paths
        self._logging_level = config.logging_config.level
        self._security_config = config.security

        self._worker_prefix = config.worker_type if config.worker_type is not None else "NAT"

        self._workers: Dict[str, Worker] = {}

    async def create_unit(self) -> str:
        # The id exists before the process does, which is what removes the need for a registration
        # handshake: the manager already knows which worker it is waiting for.
        unit_id = f"{self._worker_prefix}|{uuid.uuid4().hex}"

        worker = self._create_worker(unit_id)
        worker.start()
        self._workers[unit_id] = worker

        logger.info(f"started native worker {unit_id!r}")
        return unit_id

    async def destroy_unit(self, unit_id: str) -> None:
        worker = self._workers.pop(unit_id, None)
        if worker is None:
            return

        if worker.is_alive():
            self._signal_worker(worker)

        logger.info(f"destroyed native worker {unit_id!r}")

    async def shutdown_unit(self, unit_id: str) -> None:
        worker = self._workers.get(unit_id)
        if worker is None:
            return

        # A signal is what this manager has until the drain protocol gives it a message to send.
        if worker.is_alive():
            self._signal_worker(worker)

    async def set_unit_task_concurrency(self, unit_id: str, task_concurrency: int) -> None:
        """A worker process supplies one fixed task slot, so there is no smaller size to ask for."""

    async def poll_units(self) -> Set[str]:
        alive = set()
        for unit_id, worker in list(self._workers.items()):
            if worker.is_alive():
                alive.add(unit_id)
                continue

            worker.join()
            if worker.exitcode == 0:
                # A worker exits 0 only when it was told to stop, even though this manager was not
                # necessarily the one that asked.
                logger.info(f"native worker {unit_id!r} shut down cleanly")
            else:
                logger.warning(
                    f"native worker {unit_id!r} exited unexpectedly " f"(exitcode={describe_exitcode(worker.exitcode)})"
                )
            self._workers.pop(unit_id, None)

        return alive

    def max_units(self) -> int:
        if self._max_task_concurrency == UNLIMITED_UNITS:
            return UNLIMITED_UNITS
        return self._max_task_concurrency

    def task_concurrency_per_unit(self) -> int:
        return TASK_CONCURRENCY_PER_WORKER

    def poll_interval_seconds(self) -> float:
        return SENTINEL_POLL_INTERVAL_SECONDS

    @staticmethod
    def _signal_worker(worker: Worker) -> None:
        if sys.platform == "win32":
            # Windows os.kill with SIGINT only works for processes attached to the same console.
            # TerminateProcess is forceful: the worker's teardown (which sends
            # WorkerDisconnectNotification before exiting) does not run, so the scheduler will
            # time out the worker on its own.
            psutil.Process(worker.pid).terminate()
        else:
            os.kill(worker.pid, signal.SIGINT)

    def _create_worker(self, name: str) -> Worker:
        return Worker(
            name=name,
            address=self._worker_scheduler_address,
            object_storage_address=self._object_storage_address,
            preload=self._preload,
            capabilities=self._capabilities,
            io_threads=self._io_threads,
            task_queue_size=self._task_queue_size,
            heartbeat_interval_seconds=self._heartbeat_interval_seconds,
            task_timeout_seconds=self._task_timeout_seconds,
            death_timeout_seconds=self._death_timeout_seconds,
            garbage_collect_interval_seconds=self._garbage_collect_interval_seconds,
            trim_memory_threshold_bytes=self._trim_memory_threshold_bytes,
            hard_processor_suspend=self._hard_processor_suspend,
            event_loop=self._event_loop,
            logging_paths=self._logging_paths,
            logging_level=self._logging_level,
            worker_manager_id=self._worker_manager_id,
            security_config=self._security_config,
        )


class NativeWorkerManager:
    def __init__(self, config: NativeWorkerManagerConfig) -> None:
        self._config = config

    @property
    def config(self) -> NativeWorkerManagerConfig:
        return self._config

    def run(self) -> None:
        provisioner = NativeWorkerProvisioner(self._config)

        runner = WorkerManagerRunner(
            address=self._config.worker_manager_config.scheduler_address,
            name="worker_manager_native",
            heartbeat_interval_seconds=self._config.worker_config.heartbeat_interval_seconds,
            capabilities=self._config.worker_config.per_worker_capabilities.capabilities,
            max_provisioner_units=self._config.worker_manager_config.max_task_concurrency,
            worker_manager_id=self._config.worker_manager_config.worker_manager_id.encode(),
            worker_provisioner=provisioner,
            io_threads=self._config.worker_config.io_threads,
            security_config=self._config.security,
        )
        runner.run()
