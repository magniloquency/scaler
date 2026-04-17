import asyncio
import logging
import signal
import uuid
from typing import Dict, List, Optional, Tuple

import zmq

from scaler.config.types.zmq import ZMQConfig
from scaler.io import ymq
from scaler.io.mixins import AsyncConnector
from scaler.io.utility import create_async_connector, create_async_simple_context
from scaler.protocol.capnp import (
    BaseMessage,
    WorkerManagerCommand,
    WorkerManagerCommandResponse,
    WorkerManagerCommandType,
    WorkerManagerHeartbeat,
    WorkerManagerHeartbeatEcho,
)
from scaler.utility.event_loop import create_async_loop_routine, run_task_forever
from scaler.worker_manager_adapter.mixins import WorkerPool

Status = WorkerManagerCommandResponse.Status


class WorkerManagerRunner:
    def __init__(
        self,
        address: ZMQConfig,
        name: str,
        heartbeat_interval_seconds: int,
        capabilities: Dict[str, int],
        max_task_concurrency: int,
        worker_manager_id: bytes,
        worker_pool: WorkerPool,
    ) -> None:
        self._address = address
        self._name = name
        self._heartbeat_interval_seconds = heartbeat_interval_seconds
        self._capabilities = capabilities
        self._max_task_concurrency = max_task_concurrency
        self._worker_manager_id = worker_manager_id
        self._worker_pool = worker_pool

        self._connector_external: Optional[AsyncConnector] = None
        self._ident: bytes = b""

    def _setup_connector(self) -> None:
        self._ident = f"{self._name}|{uuid.uuid4().bytes.hex()}".encode()
        context = create_async_simple_context()
        self._connector_external = create_async_connector(
            context,
            name=self._name,
            socket_type=zmq.DEALER,
            address=self._address,
            bind_or_connect="connect",
            callback=self._on_receive_external,
            identity=self._ident,
        )

    def run(self) -> None:
        self._loop = asyncio.new_event_loop()
        run_task_forever(self._loop, self._run(), cleanup_callback=self._cleanup)

    def _cleanup(self) -> None:
        if self._connector_external is not None:
            self._connector_external.destroy()

    def _destroy(self) -> None:
        print(f"Worker manager {self._ident!r} received signal, shutting down")
        self._task.cancel()

    def _register_signal(self) -> None:
        self._loop.add_signal_handler(signal.SIGINT, self._destroy)
        self._loop.add_signal_handler(signal.SIGTERM, self._destroy)

    async def _run(self) -> None:
        self._setup_connector()
        self._task = self._loop.create_task(self._get_loops())
        self._register_signal()
        await self._task

    async def _send_heartbeat(self) -> None:
        await self._connector_external.send(
            WorkerManagerHeartbeat(
                maxTaskConcurrency=self._max_task_concurrency,
                capabilities=self._capabilities,
                workerManagerID=self._worker_manager_id,
            )
        )

    async def _get_loops(self) -> None:
        loops = [
            create_async_loop_routine(self._connector_external.routine, 0),
            create_async_loop_routine(self._send_heartbeat, self._heartbeat_interval_seconds),
        ]

        try:
            await asyncio.gather(*loops)
        except asyncio.CancelledError:
            pass
        except ymq.YMQException as e:
            if e.code == ymq.ErrorCode.ConnectorSocketClosedByRemoteEnd:
                pass
            else:
                logging.exception(f"{self._ident!r}: failed with unhandled exception:\n{e}")
        except Exception:
            logging.exception(f"{self._ident!r}: failed with unhandled exception")

    async def _on_receive_external(self, message: BaseMessage) -> None:
        if isinstance(message, WorkerManagerCommand):
            await self._handle_command(message)
        elif isinstance(message, WorkerManagerHeartbeatEcho):
            pass
        else:
            logging.warning(f"Received unknown message type: {type(message)}")

    async def _handle_command(self, command: WorkerManagerCommand) -> None:
        cmd_type = command.command
        response_status: Status = Status.success
        worker_ids: List[bytes] = []
        capabilities: Dict[str, int] = {}

        if cmd_type == WorkerManagerCommandType.startWorkers:
            worker_ids, response_status = await self._worker_pool.start_worker()
            if response_status == Status.success:
                capabilities = self._capabilities
        elif cmd_type == WorkerManagerCommandType.shutdownWorkers:
            worker_ids, response_status = await self._worker_pool.shutdown_workers(list(command.workerIDs))
        else:
            raise ValueError(f"Unknown WorkerManagerCommand: {cmd_type!r}")

        await self._connector_external.send(
            WorkerManagerCommandResponse(
                command=cmd_type, status=response_status, workerIDs=worker_ids, capabilities=capabilities
            )
        )

    async def start_worker(self) -> Tuple[List[bytes], Status]:
        return await self._worker_pool.start_worker()

    async def shutdown_workers(self, worker_ids: List[bytes]) -> Tuple[List[bytes], Status]:
        return await self._worker_pool.shutdown_workers(worker_ids)
