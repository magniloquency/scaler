import asyncio
import logging
import signal
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Tuple

from scaler.io import ymq
from scaler.io.mixins import AsyncConnector
from scaler.protocol.capnp import (
    BaseMessage,
    WorkerManagerCommand,
    WorkerManagerCommandResponse,
    WorkerManagerCommandType,
    WorkerManagerHeartbeat,
    WorkerManagerHeartbeatEcho,
)
from scaler.utility.event_loop import create_async_loop_routine, run_task_forever

Status = WorkerManagerCommandResponse.Status


class BaseWorkerManager(ABC):
    _heartbeat_interval_seconds: int
    _capabilities: Dict[str, int]
    _max_task_concurrency: int
    _worker_manager_id: bytes
    _connector_external: Optional[AsyncConnector]
    _ident: bytes

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
            worker_ids, response_status = await self.start_worker()
            if response_status == Status.success:
                capabilities = self._capabilities
        elif cmd_type == WorkerManagerCommandType.shutdownWorkers:
            worker_ids, response_status = await self.shutdown_workers(list(command.workerIDs))
        else:
            raise ValueError(f"Unknown WorkerManagerCommand: {cmd_type!r}")

        await self._connector_external.send(
            WorkerManagerCommandResponse(
                command=cmd_type, status=response_status, workerIDs=worker_ids, capabilities=capabilities
            )
        )

    @abstractmethod
    async def start_worker(self) -> Tuple[List[bytes], Status]: ...

    @abstractmethod
    async def shutdown_workers(self, worker_ids: List[bytes]) -> Tuple[List[bytes], Status]: ...
