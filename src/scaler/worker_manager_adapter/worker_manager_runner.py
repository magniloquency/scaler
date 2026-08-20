import asyncio
import logging
from typing import Dict, Optional, Union

from scaler.config.common.security import SecurityConfig
from scaler.config.types.address import AddressConfig
from scaler.io import ymq
from scaler.io.mixins import AsyncConnector, ConnectorRemoteType, NetworkBackend
from scaler.io.network_backends import get_network_backend_from_env
from scaler.io.utility import generate_identity_from_name
from scaler.protocol.capnp import BaseMessage, WorkerManagerCommand, WorkerManagerHeartbeat, WorkerManagerHeartbeatEcho
from scaler.protocol.helpers import dict_to_capabilities
from scaler.utility.event_loop import create_async_loop_routine, run_task_forever
from scaler.utility.signal_handler import install_async_shutdown_handler
from scaler.worker_manager_adapter.common import extract_desired_count
from scaler.worker_manager_adapter.mixins import DeclarativeWorkerProvisioner
from scaler.worker_manager_adapter.unit_controller import UnitController
from scaler.worker_manager_adapter.unit_provisioner import UnitProvisioner

logger = logging.getLogger(__name__)

DEFAULT_DRAIN_TIMEOUT_SECONDS = 60.0
DEFAULT_RESTART_BACKOFF_SECONDS = 1.0


class WorkerManagerRunner:
    def __init__(
        self,
        address: AddressConfig,
        name: str,
        heartbeat_interval_seconds: int,
        capabilities: Dict[str, int],
        max_provisioner_units: int,
        worker_manager_id: bytes,
        worker_provisioner: Union[UnitProvisioner, DeclarativeWorkerProvisioner],
        io_threads: int = 1,
        workers_per_provisioner_unit: int = 1,
        security_config: Optional[SecurityConfig] = None,
        drain_timeout_seconds: float = DEFAULT_DRAIN_TIMEOUT_SECONDS,
        restart_backoff_seconds: float = DEFAULT_RESTART_BACKOFF_SECONDS,
    ) -> None:
        self._address = address
        self._name = name
        self._heartbeat_interval_seconds = heartbeat_interval_seconds
        self._capabilities = capabilities
        self._max_provisioner_units = max_provisioner_units
        self._worker_manager_id = worker_manager_id
        self._io_threads = io_threads
        self._workers_per_provisioner_unit = workers_per_provisioner_unit
        self._security_config = security_config

        # UnitController owns the fleet for a converted provisioner. The others still drive
        # themselves through set_desired_task_concurrency until they are converted too.
        self._unit_provisioner: Optional[UnitProvisioner] = None
        self._legacy_provisioner: Optional[DeclarativeWorkerProvisioner] = None
        self._unit_controller: Optional[UnitController] = None

        if isinstance(worker_provisioner, UnitProvisioner):
            self._unit_provisioner = worker_provisioner
            self._unit_controller = UnitController(worker_provisioner, drain_timeout_seconds, restart_backoff_seconds)
        else:
            self._legacy_provisioner = worker_provisioner

        self._backend: Optional[NetworkBackend] = None
        self._connector_external: Optional[AsyncConnector] = None
        self._ident: bytes = b""
        self._task: Optional[asyncio.Task] = None

    async def _initialize_network(self) -> None:
        self._ident = generate_identity_from_name(self._name)
        self._backend = get_network_backend_from_env(io_threads=self._io_threads)
        self._connector_external = self._backend.create_async_connector(
            identity=self._ident, callback=self._on_receive_external
        )

    def run(self) -> None:
        self._loop = asyncio.new_event_loop()
        run_task_forever(self._loop, self._run(), cleanup_callback=self.cleanup)

    async def run_in_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Run using an externally-managed loop. The caller is responsible for catching asyncio.CancelledError."""
        self._loop = loop
        await self._run()

    def cleanup(self) -> None:
        if self._connector_external is not None:
            self._connector_external.destroy()

    def _destroy(self) -> None:
        logger.info(f"Worker manager {self._ident!r} received signal, shutting down")
        self._task.cancel()

    def _register_signal(self) -> None:
        install_async_shutdown_handler(self._loop, self._destroy)

    async def _run(self) -> None:
        self._task = self._loop.create_task(self._get_loops())
        await self._task

    async def _send_heartbeat(self) -> None:
        await self._connector_external.send(
            WorkerManagerHeartbeat(
                maxTaskConcurrency=self._max_provisioner_units * self._workers_per_provisioner_unit,
                capabilities=dict_to_capabilities(self._capabilities),
                workerManagerID=self._worker_manager_id,
            ),
            detached=True,
        )

    async def _get_loops(self) -> None:
        await self._initialize_network()
        await self._connector_external.connect(
            self._address, ConnectorRemoteType.Binder, security_config=self._security_config
        )
        self._register_signal()

        loops = [
            create_async_loop_routine(self._connector_external.routine, 0),
            create_async_loop_routine(self._send_heartbeat, self._heartbeat_interval_seconds),
        ]

        if self._unit_controller is not None and self._unit_provisioner is not None:
            loops.append(
                create_async_loop_routine(
                    self._unit_controller.routine,
                    self._unit_provisioner.poll_interval_seconds(),
                    swallow_routine_errors=True,
                )
            )

        try:
            await asyncio.gather(*loops)
        except asyncio.CancelledError:
            pass
        except ymq.YMQException as e:
            if e.code == ymq.ErrorCode.ConnectorSocketClosedByRemoteEnd:
                pass
            else:
                logger.exception(f"{self._ident!r}: failed with unhandled exception:\n{e}")
        except Exception:
            logger.exception(f"{self._ident!r}: failed with unhandled exception")

        if self._unit_controller is not None:
            await self._unit_controller.drain_all()
        elif self._legacy_provisioner is not None:
            await self._legacy_provisioner.terminate()

    async def _on_receive_external(self, message: BaseMessage) -> None:
        try:
            if isinstance(message, WorkerManagerCommand):
                await self._handle_command(message)
            elif isinstance(message, WorkerManagerHeartbeatEcho):
                pass
            else:
                logger.warning(f"Unknown action: received unrecognized message type {type(message).__name__!r}")
        except Exception:
            logger.exception(f"Unhandled exception while processing message {type(message).__name__}")

    async def _handle_command(self, command: WorkerManagerCommand) -> None:
        requests = getattr(command, "setDesiredTaskConcurrencyRequests", None)
        if requests is None:
            logger.warning("Unknown action: received WorkerManagerCommand with no recognized payload")
            return

        if self._unit_controller is None:
            if self._legacy_provisioner is not None:
                await self._legacy_provisioner.set_desired_task_concurrency(list(requests))
            return

        # The capability match happens once, here, rather than in every provisioner.
        self._unit_controller.set_desired_task_concurrency(extract_desired_count(list(requests), self._capabilities))
