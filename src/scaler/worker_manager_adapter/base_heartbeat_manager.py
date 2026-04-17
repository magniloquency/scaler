import time
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Dict, List, Optional

import psutil

from scaler.config.types.object_storage_server import ObjectStorageAddressConfig
from scaler.io.mixins import AsyncConnector, AsyncObjectStorageConnector
from scaler.protocol.capnp import Resource, WorkerHeartbeat, WorkerHeartbeatEcho
from scaler.utility.mixins import Looper
from scaler.worker.agent.mixins import HeartbeatManager, TimeoutManager

if TYPE_CHECKING:
    from scaler.worker_manager_adapter.base_task_manager import BaseTaskManager


class BaseHeartbeatManager(Looper, HeartbeatManager, ABC):
    def __init__(
        self,
        object_storage_address: Optional[ObjectStorageAddressConfig],
        capabilities: Dict[str, int],
        task_queue_size: int,
        worker_manager_id: bytes,
    ) -> None:
        self._capabilities = capabilities
        self._task_queue_size = task_queue_size
        self._worker_manager_id = worker_manager_id

        self._agent_process = psutil.Process()

        self._connector_external: Optional[AsyncConnector] = None
        self._connector_storage: Optional[AsyncObjectStorageConnector] = None
        self._task_manager: Optional["BaseTaskManager"] = None
        self._timeout_manager: Optional[TimeoutManager] = None

        self._start_timestamp_ns = 0
        self._latency_us = 0

        self._object_storage_address: Optional[ObjectStorageAddressConfig] = object_storage_address

    def register(
        self,
        connector_external: AsyncConnector,
        connector_storage: AsyncObjectStorageConnector,
        worker_task_manager: "BaseTaskManager",
        timeout_manager: TimeoutManager,
    ) -> None:
        self._connector_external = connector_external
        self._connector_storage = connector_storage
        self._task_manager = worker_task_manager
        self._timeout_manager = timeout_manager

    async def on_heartbeat_echo(self, heartbeat: WorkerHeartbeatEcho) -> None:
        if self._start_timestamp_ns == 0:
            return

        self._latency_us = int(((time.time_ns() - self._start_timestamp_ns) / 2) // 1_000)
        self._start_timestamp_ns = 0
        self._timeout_manager.update_last_seen_time()

        if self._object_storage_address is None:
            address_message = heartbeat.objectStorageAddress
            self._object_storage_address = ObjectStorageAddressConfig(address_message.host, address_message.port)
            await self._connector_storage.connect(self._object_storage_address.host, self._object_storage_address.port)

    def get_object_storage_address(self) -> Optional[ObjectStorageAddressConfig]:
        return self._object_storage_address

    @abstractmethod
    def _get_processor_statuses(self) -> List: ...

    async def routine(self) -> None:
        if self._start_timestamp_ns != 0:
            return

        await self._connector_external.send(
            WorkerHeartbeat(
                agent=Resource(
                    cpu=int(self._agent_process.cpu_percent() * 10), rss=self._agent_process.memory_info().rss
                ),
                rssFree=psutil.virtual_memory().available,
                queueSize=self._task_queue_size,
                queuedTasks=self._task_manager.get_queued_size(),
                latencyUS=self._latency_us,
                taskLock=self._task_manager.can_accept_task(),
                processors=self._get_processor_statuses(),
                capabilities=self._capabilities,
                workerManagerID=self._worker_manager_id,
            )
        )
        self._start_timestamp_ns = time.time_ns()
