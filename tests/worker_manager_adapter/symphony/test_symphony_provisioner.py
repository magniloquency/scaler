from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, MagicMock, patch

try:
    from scaler.worker_manager_adapter.symphony.worker_manager import SymphonyWorkerProvisioner

    _SYMPHONY_AVAILABLE = True
except ImportError:
    _SYMPHONY_AVAILABLE = False


def _make_provisioner(max_task_concurrency: int = -1) -> SymphonyWorkerProvisioner:
    config = MagicMock()
    config.worker_config.per_worker_capabilities.capabilities = {}
    config.worker_manager_config.max_task_concurrency = max_task_concurrency
    config.worker_manager_config.worker_manager_id = "test-wm"
    config.service_name = "test-service"
    return SymphonyWorkerProvisioner(config)


def _make_request(task_concurrency: int, capabilities: dict) -> MagicMock:
    request = MagicMock()
    request.taskConcurrency = task_concurrency
    request.capabilities = [MagicMock(key=k, value=v) for k, v in capabilities.items()]
    return request


@unittest.skipUnless(_SYMPHONY_AVAILABLE, "soamapi not installed")
class TestSymphonyWorkerProvisionerConcurrencyConversion(unittest.IsolatedAsyncioTestCase):
    async def test_passes_task_concurrency_directly_as_desired_count(self) -> None:
        provisioner = _make_provisioner()
        request = _make_request(task_concurrency=4, capabilities={})
        with patch.object(provisioner._reconcile_loop, "_reconcile", new_callable=AsyncMock):
            await provisioner.set_desired_task_concurrency([request])
        self.assertEqual(provisioner._reconcile_loop._desired_count, 4)

    async def test_desired_count_is_zero_when_no_matching_requests(self) -> None:
        provisioner = _make_provisioner()
        with patch.object(provisioner._reconcile_loop, "_reconcile", new_callable=AsyncMock):
            await provisioner.set_desired_task_concurrency([])
        self.assertEqual(provisioner._reconcile_loop._desired_count, 0)

    async def test_max_task_concurrency_wired_to_reconcile_loop(self) -> None:
        provisioner = _make_provisioner(max_task_concurrency=3)
        self.assertEqual(provisioner._reconcile_loop._max_units, 3)
