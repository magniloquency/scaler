from typing import List

from scaler.worker_manager_adapter.mixins import ProcessorStatusProvider


class SymphonyProcessorStatusProvider(ProcessorStatusProvider):
    def get_processor_statuses(self) -> List:
        return []
