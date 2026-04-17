import logging
import os
import signal
import uuid
from typing import Dict, List, Tuple

import zmq

from scaler.config.section.symphony_worker_manager import SymphonyWorkerManagerConfig
from scaler.io.utility import create_async_connector, create_async_simple_context
from scaler.protocol.capnp import WorkerManagerCommandResponse
from scaler.utility.identifiers import WorkerID
from scaler.worker_manager_adapter.base_manager import BaseWorkerManager
from scaler.worker_manager_adapter.symphony.worker import SymphonyWorker

Status = WorkerManagerCommandResponse.Status


class SymphonyWorkerManager(BaseWorkerManager):
    def __init__(self, config: SymphonyWorkerManagerConfig):
        self._address = config.worker_manager_config.scheduler_address
        self._worker_scheduler_address = config.worker_manager_config.effective_worker_scheduler_address
        self._object_storage_address = config.worker_manager_config.object_storage_address
        self._service_name = config.service_name
        self._max_task_concurrency = config.worker_manager_config.max_task_concurrency
        self._worker_manager_id = config.worker_manager_config.worker_manager_id.encode()
        self._capabilities = config.worker_config.per_worker_capabilities.capabilities
        self._io_threads = config.worker_config.io_threads
        self._task_queue_size = config.worker_config.per_worker_task_queue_size
        self._heartbeat_interval_seconds = config.worker_config.heartbeat_interval_seconds
        self._death_timeout_seconds = config.worker_config.death_timeout_seconds
        self._event_loop = config.worker_config.event_loop

        context = create_async_simple_context()
        self._name = "worker_manager_symphony"
        self._ident = f"{self._name}|{uuid.uuid4().bytes.hex()}".encode()

        self._connector_external = create_async_connector(
            context,
            name="worker_manager_symphony",
            socket_type=zmq.DEALER,
            address=self._address,
            bind_or_connect="connect",
            callback=self._on_receive_external,
            identity=self._ident,
        )

        self._workers: Dict[WorkerID, SymphonyWorker] = {}

    async def start_worker(self) -> Tuple[List[bytes], Status]:
        if len(self._workers) >= self._max_task_concurrency != -1:
            return [], Status.tooManyWorkers

        worker = SymphonyWorker(
            name=f"SYM|{uuid.uuid4().hex}",
            address=self._worker_scheduler_address,
            object_storage_address=self._object_storage_address,
            service_name=self._service_name,
            base_concurrency=self._max_task_concurrency,
            capabilities=self._capabilities,
            io_threads=self._io_threads,
            task_queue_size=self._task_queue_size,
            heartbeat_interval_seconds=self._heartbeat_interval_seconds,
            death_timeout_seconds=self._death_timeout_seconds,
            event_loop=self._event_loop,
            worker_manager_id=self._worker_manager_id,
        )

        worker.start()
        self._workers[worker.identity] = worker
        return [bytes(worker.identity)], Status.success

    async def shutdown_workers(self, worker_ids: List[bytes]) -> Tuple[List[bytes], Status]:
        if not worker_ids:
            return [], Status.workerNotFound

        for wid_bytes in worker_ids:
            wid = WorkerID(wid_bytes)
            if wid not in self._workers:
                logging.warning(f"Worker with ID {wid!r} does not exist.")
                return [], Status.workerNotFound

        for wid_bytes in worker_ids:
            wid = WorkerID(wid_bytes)
            worker = self._workers.pop(wid)
            os.kill(worker.pid, signal.SIGINT)
            worker.join()

        return list(worker_ids), Status.success
