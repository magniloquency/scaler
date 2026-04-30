from __future__ import annotations

import asyncio
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
class TestSymphonyWorkerProvisionerReconcile(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.provisioner = _make_provisioner()

    async def test_reconcile_increases_worker_count(self) -> None:
        self.provisioner._desired_count = 2
        with patch.object(self.provisioner, "start_units", new_callable=AsyncMock) as start_mock:
            with patch.object(self.provisioner, "stop_units", new_callable=AsyncMock) as stop_mock:
                await self.provisioner._reconcile()
                start_mock.assert_called_once_with(2)
                stop_mock.assert_not_called()

    async def test_reconcile_decreases_worker_count(self) -> None:
        self.provisioner._workers = [MagicMock(), MagicMock(), MagicMock()]
        self.provisioner._desired_count = 1
        with patch.object(self.provisioner, "start_units", new_callable=AsyncMock) as start_mock:
            with patch.object(self.provisioner, "stop_units", new_callable=AsyncMock) as stop_mock:
                await self.provisioner._reconcile()
                start_mock.assert_not_called()
                stop_mock.assert_called_once_with(2)

    async def test_reconcile_no_change(self) -> None:
        self.provisioner._workers = [MagicMock()]
        self.provisioner._desired_count = 1
        with patch.object(self.provisioner, "start_units", new_callable=AsyncMock) as start_mock:
            with patch.object(self.provisioner, "stop_units", new_callable=AsyncMock) as stop_mock:
                await self.provisioner._reconcile()
                start_mock.assert_not_called()
                stop_mock.assert_not_called()

    async def test_reconcile_respects_max_task_concurrency(self) -> None:
        provisioner = _make_provisioner(max_task_concurrency=3)
        provisioner._desired_count = 10
        with patch.object(provisioner, "start_units", new_callable=AsyncMock) as start_mock:
            with patch.object(provisioner, "stop_units", new_callable=AsyncMock) as stop_mock:
                await provisioner._reconcile()
                start_mock.assert_called_once_with(3)
                stop_mock.assert_not_called()

    async def test_set_desired_task_concurrency_triggers_reconcile(self) -> None:
        request = _make_request(task_concurrency=4, capabilities={})
        with patch.object(self.provisioner, "_reconcile", new_callable=AsyncMock) as reconcile_mock:
            await self.provisioner.set_desired_task_concurrency([request])
            self.assertIsNotNone(self.provisioner._pending_reconcile_task)
            await asyncio.sleep(0)
        self.assertEqual(self.provisioner._desired_count, 4)
        reconcile_mock.assert_called_once()

    async def test_set_desired_task_concurrency_coalesces_rapid_calls(self) -> None:
        request = _make_request(task_concurrency=5, capabilities={})
        with patch.object(self.provisioner, "_reconcile", new_callable=AsyncMock) as reconcile_mock:
            await self.provisioner.set_desired_task_concurrency([request])
            await self.provisioner.set_desired_task_concurrency([request])
            await self.provisioner.set_desired_task_concurrency([request])
            await asyncio.sleep(0)
        reconcile_mock.assert_called_once()
