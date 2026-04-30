import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from scaler.worker_manager_adapter.aws_hpc.worker_manager import BatchWorkerProvisioner


def _make_provisioner(max_concurrent_jobs: int = 100) -> BatchWorkerProvisioner:
    config = MagicMock()
    config.worker_config.per_worker_capabilities.capabilities = {}
    config.max_concurrent_jobs = max_concurrent_jobs
    return BatchWorkerProvisioner(config)


def _make_request(task_concurrency: int, capabilities: dict) -> MagicMock:
    request = MagicMock()
    request.taskConcurrency = task_concurrency
    request.capabilities = [MagicMock(key=k, value=v) for k, v in capabilities.items()]
    return request


class TestBatchWorkerProvisionerReconcile(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.provisioner = _make_provisioner()

    async def test_reconcile_starts_units(self) -> None:
        self.provisioner._desired_count = 2
        with patch.object(self.provisioner, "start_units", new_callable=AsyncMock) as start_mock:
            with patch.object(self.provisioner, "stop_units", new_callable=AsyncMock) as stop_mock:
                await self.provisioner._reconcile()
                start_mock.assert_called_once_with(2)
                stop_mock.assert_not_called()

    async def test_reconcile_stops_units(self) -> None:
        self.provisioner._units = [MagicMock(), MagicMock()]
        self.provisioner._desired_count = 0
        with patch.object(self.provisioner, "start_units", new_callable=AsyncMock) as start_mock:
            with patch.object(self.provisioner, "stop_units", new_callable=AsyncMock) as stop_mock:
                await self.provisioner._reconcile()
                start_mock.assert_not_called()
                stop_mock.assert_called_once_with(2)

    async def test_reconcile_no_change(self) -> None:
        self.provisioner._units = [MagicMock()]
        self.provisioner._desired_count = 1
        with patch.object(self.provisioner, "start_units", new_callable=AsyncMock) as start_mock:
            with patch.object(self.provisioner, "stop_units", new_callable=AsyncMock) as stop_mock:
                await self.provisioner._reconcile()
                start_mock.assert_not_called()
                stop_mock.assert_not_called()

    async def test_set_desired_task_concurrency_converts_to_process_count(self) -> None:
        provisioner = _make_provisioner(max_concurrent_jobs=100)
        request = _make_request(task_concurrency=150, capabilities={})
        with patch.object(provisioner, "_reconcile", new_callable=AsyncMock):
            await provisioner.set_desired_task_concurrency([request])
            await asyncio.sleep(0)
        self.assertEqual(provisioner._desired_count, 2)  # ceil(150 / 100) = 2

    async def test_set_desired_task_concurrency_zero_when_no_requests(self) -> None:
        with patch.object(self.provisioner, "_reconcile", new_callable=AsyncMock):
            await self.provisioner.set_desired_task_concurrency([])
            await asyncio.sleep(0)
        self.assertEqual(self.provisioner._desired_count, 0)

    async def test_set_desired_task_concurrency_triggers_reconcile(self) -> None:
        request = _make_request(task_concurrency=50, capabilities={})
        with patch.object(self.provisioner, "_reconcile", new_callable=AsyncMock) as reconcile_mock:
            await self.provisioner.set_desired_task_concurrency([request])
            self.assertIsNotNone(self.provisioner._pending_reconcile_task)
            await asyncio.sleep(0)
        reconcile_mock.assert_called_once()

    async def test_set_desired_task_concurrency_coalesces_rapid_calls(self) -> None:
        request = _make_request(task_concurrency=50, capabilities={})
        with patch.object(self.provisioner, "_reconcile", new_callable=AsyncMock) as reconcile_mock:
            await self.provisioner.set_desired_task_concurrency([request])
            await self.provisioner.set_desired_task_concurrency([request])
            await self.provisioner.set_desired_task_concurrency([request])
            await asyncio.sleep(0)
        reconcile_mock.assert_called_once()
