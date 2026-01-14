import logging
import multiprocessing

from aiohttp import web

from scaler.config.common.web import WebConfig
from scaler.config.common.worker_adapter import WorkerAdapterConfig
from scaler.config.section.cluster import ClusterConfig
from scaler.config.section.fixed_native_worker_adapter import FixedNativeWorkerAdapterConfig
from scaler.utility.logging.utility import setup_logger
from scaler.utility.network_util import get_available_tcp_port
from scaler.worker_adapter.fixed_native import FixedNativeWorkerAdapter


class Cluster(multiprocessing.get_context("spawn").Process):  # type: ignore[misc]
    def __init__(self, config: ClusterConfig):
        multiprocessing.Process.__init__(self, name="WorkerMaster")

        self._address = config.scheduler_address
        self._object_storage_address = config.object_storage_address
        self._preload = config.preload
        self._worker_io_threads = config.worker_io_threads
        self._worker_names = config.worker_names.names
        self._per_worker_capabilities = config.worker_config.per_worker_capabilities.capabilities

        self._per_worker_task_queue_size = config.worker_config.per_worker_task_queue_size
        self._heartbeat_interval_seconds = config.worker_config.heartbeat_interval_seconds
        self._task_timeout_seconds = config.worker_config.task_timeout_seconds
        self._death_timeout_seconds = config.worker_config.death_timeout_seconds
        self._garbage_collect_interval_seconds = config.worker_config.garbage_collect_interval_seconds
        self._trim_memory_threshold_bytes = config.worker_config.trim_memory_threshold_bytes
        self._hard_processor_suspend = config.worker_config.hard_processor_suspend
        self._event_loop = config.event_loop

        self._logging_paths = config.logging_config.paths
        self._logging_config_file = config.logging_config.config_file
        self._logging_level = config.logging_config.level

        self._worker_adapter = FixedNativeWorkerAdapter(
            FixedNativeWorkerAdapterConfig(
                web_config=WebConfig(adapter_web_host=None, adapter_web_port=None),
                preload=config.preload,
                worker_adapter_config=WorkerAdapterConfig(
                    scheduler_address=config.scheduler_address,
                    object_storage_address=config.object_storage_address,
                    max_workers=len(config.worker_names),
                ),
                worker_config=config.worker_config,
                logging_config=config.logging_config,
                event_loop=config.event_loop,
                worker_io_threads=config.worker_io_threads,
            )
        )

    def run(self):
        setup_logger(self._logging_paths, self._logging_config_file, self._logging_level)
        self.__start_workers_and_run_forever()

    async def __destroy(self, app):
        logging.info(f"{self.__get_prefix()} received signal, shutting down")
        self._worker_adapter.shutdown()

    def __start_workers_and_run_forever(self):
        logging.info(
            f"{self.__get_prefix()} starting {len(self._worker_names)} workers, heartbeat_interval_seconds="
            f"{self._heartbeat_interval_seconds}, task_timeout_seconds={self._task_timeout_seconds}"
        )

        self._worker_adapter.start()
        app = self._worker_adapter.create_app()
        app.on_shutdown.append(self.__destroy)

        # the fixed native worker adapter doesn't actually support spawning and shutting down workers dynamically,
        # but we run the server here to keep the interface consistent
        # it may become useful in the future
        web.run_app(app, host="127.0.0.1", port=get_available_tcp_port(), reuse_address=True, reuse_port=True)
        logging.info(f"{self.__get_prefix()} shutdown")

    def __get_prefix(self):
        return f"{self.__class__.__name__}:"
