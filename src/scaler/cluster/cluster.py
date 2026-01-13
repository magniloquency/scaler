import logging
import multiprocessing

from aiohttp import web

from scaler.config.common.worker_adapter import WorkerAdapterConfig
from scaler.config.section.cluster import ClusterConfig
from scaler.utility.logging.utility import setup_logger
from scaler.worker_adapter.native import NativeWorkerAdapter, NativeWorkerAdapterConfig


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

        self._web_config = config.web_config

        self._worker_adapter = NativeWorkerAdapter(
            NativeWorkerAdapterConfig(
                web_config=config.web_config,
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

    async def __on_shutdown(self, app):
        logging.info(f"{self.__get_prefix()} received signal, shutting down")
        self._worker_adapter.shutdown()

    def __start_workers_and_run_forever(self):
        app = self._worker_adapter.create_app()
        app.on_shutdown.append(self.__on_shutdown)
        web.run_app(
            app=app,
            host=self._web_config.adapter_web_host,
            port=self._web_config.adapter_web_port,
            reuse_address=True,
            reuse_port=True,
        )

    def __get_prefix(self):
        return f"{self.__class__.__name__}:"
