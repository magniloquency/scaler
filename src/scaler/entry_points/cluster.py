import dataclasses

from scaler.config.section.native_worker_adapter import NativeWorkerAdapterConfig, NativeWorkerAdapterMode
from scaler.worker_manager_adapter.baremetal.native import NativeWorkerAdapter


def main() -> None:
    config = NativeWorkerAdapterConfig.parse("Scaler Cluster", "cluster")
    config = dataclasses.replace(config, mode=NativeWorkerAdapterMode.FIXED)
    NativeWorkerAdapter(config).run()


__all__ = ["main"]
