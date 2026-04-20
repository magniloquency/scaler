from typing import List

from scaler.protocol.capnp import ProcessorStatus
from scaler.worker_manager_adapter.mixins import ProcessorStatusProvider


class SymphonyProcessorStatusProvider(ProcessorStatusProvider):
    def get_processor_statuses(self) -> List[ProcessorStatus]:
        return []
