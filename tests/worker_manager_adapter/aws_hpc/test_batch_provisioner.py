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


class TestBatchWorkerProvisionerConcurrencyConversion(unittest.IsolatedAsyncioTestCase):
    async def test_converts_task_concurrency_to_process_count(self) -> None:
        provisioner = _make_provisioner(max_concurrent_jobs=100)
        request = _make_request(task_concurrency=150, capabilities={})
        with patch.object(provisioner._reconcile_loop, "_reconcile", new_callable=AsyncMock):
            await provisioner.set_desired_task_concurrency([request])
        self.assertEqual(provisioner._reconcile_loop._desired_unit_count, 2)  # ceil(150 / 100) = 2

    async def test_rounds_up_fractional_process_count(self) -> None:
        provisioner = _make_provisioner(max_concurrent_jobs=100)
        request = _make_request(task_concurrency=1, capabilities={})
        with patch.object(provisioner._reconcile_loop, "_reconcile", new_callable=AsyncMock):
            await provisioner.set_desired_task_concurrency([request])
        self.assertEqual(provisioner._reconcile_loop._desired_unit_count, 1)  # ceil(1 / 100) = 1

    async def test_task_concurrency_zero_sets_desired_to_zero(self) -> None:
        provisioner = _make_provisioner()
        with patch.object(provisioner._reconcile_loop, "_reconcile", new_callable=AsyncMock):
            await provisioner.set_desired_task_concurrency([_make_request(task_concurrency=100, capabilities={})])
        self.assertEqual(provisioner._reconcile_loop._desired_unit_count, 1)
        with patch.object(provisioner._reconcile_loop, "_reconcile", new_callable=AsyncMock):
            await provisioner.set_desired_task_concurrency([_make_request(task_concurrency=0, capabilities={})])
        self.assertEqual(provisioner._reconcile_loop._desired_unit_count, 0)


class TestBatchWorkerProvisionerScalingThroughReconcileLoop(unittest.IsolatedAsyncioTestCase):
    async def test_scale_up_creates_units(self) -> None:
        provisioner = _make_provisioner(max_concurrent_jobs=100)

        def fake_start_unit() -> None:
            provisioner._units.append(MagicMock())

        with patch.object(provisioner, "_start_unit", side_effect=fake_start_unit):
            await provisioner.set_desired_task_concurrency([_make_request(task_concurrency=200, capabilities={})])
            await asyncio.sleep(0)  # ceil(200 / 100) = 2 units
        self.assertEqual(len(provisioner._units), 2)

    async def test_scale_down_terminates_units(self) -> None:
        provisioner = _make_provisioner(max_concurrent_jobs=100)
        units = [MagicMock() for _ in range(3)]
        provisioner._units = units[:]
        await provisioner.set_desired_task_concurrency([_make_request(task_concurrency=100, capabilities={})])
        await asyncio.sleep(0)  # current=3, desired=1 → stop_units(2)
        self.assertEqual(len(provisioner._units), 1)
        units[0].terminate.assert_called_once()
        units[1].terminate.assert_called_once()
        units[2].terminate.assert_not_called()
