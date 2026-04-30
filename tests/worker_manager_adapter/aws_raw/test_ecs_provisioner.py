import asyncio
import math
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from scaler.worker_manager_adapter.aws_raw.ecs import ECSWorkerProvisioner


def _make_provisioner(max_task_concurrency: int = -1, ecs_task_cpu: int = 4) -> ECSWorkerProvisioner:
    config = MagicMock()
    config.worker_config.per_worker_capabilities.capabilities = {}
    config.worker_manager_config.max_task_concurrency = max_task_concurrency
    config.worker_manager_config.worker_manager_id = "test-wm"
    config.ecs_task_cpu = ecs_task_cpu
    config.ecs_cluster = "test-cluster"
    config.ecs_task_definition = "test-td"
    config.ecs_subnets = ["subnet-123"]
    config.aws_access_key_id = "key"
    config.aws_secret_access_key = "secret"
    config.aws_region = "us-east-1"

    with patch("boto3.Session"):
        provisioner = ECSWorkerProvisioner.__new__(ECSWorkerProvisioner)
        provisioner._capabilities = {}
        provisioner._ecs_task_cpu = ecs_task_cpu
        provisioner._max_task_concurrency = max_task_concurrency
        provisioner._max_instances = (
            math.ceil(max_task_concurrency / ecs_task_cpu) if max_task_concurrency != -1 else -1
        )
        provisioner._units = []
        provisioner._desired_count = 0
        import asyncio

        provisioner._reconcile_lock = asyncio.Lock()
        provisioner._pending_reconcile_task = None
        provisioner._active_reconcile_task = None
        provisioner._ecs_client = MagicMock()
        provisioner._ecs_cluster = "test-cluster"
        provisioner._ecs_task_definition = "test-td"
        provisioner._ecs_subnets = ["subnet-123"]

    return provisioner


def _make_request(task_concurrency: int, capabilities: dict) -> MagicMock:
    request = MagicMock()
    request.taskConcurrency = task_concurrency
    request.capabilities = [MagicMock(key=k, value=v) for k, v in capabilities.items()]
    return request


class TestECSWorkerProvisionerReconcile(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.provisioner = _make_provisioner()

    async def test_reconcile_increases_unit_count(self) -> None:
        self.provisioner._desired_count = 2
        with patch.object(self.provisioner, "start_units", new_callable=AsyncMock) as start_mock:
            with patch.object(self.provisioner, "stop_units", new_callable=AsyncMock) as stop_mock:
                await self.provisioner._reconcile()
                start_mock.assert_called_once_with(2)
                stop_mock.assert_not_called()

    async def test_reconcile_decreases_unit_count(self) -> None:
        self.provisioner._units = ["arn:1", "arn:2", "arn:3"]
        self.provisioner._desired_count = 1
        with patch.object(self.provisioner, "start_units", new_callable=AsyncMock) as start_mock:
            with patch.object(self.provisioner, "stop_units", new_callable=AsyncMock) as stop_mock:
                await self.provisioner._reconcile()
                start_mock.assert_not_called()
                stop_mock.assert_called_once_with(2)

    async def test_reconcile_no_change(self) -> None:
        self.provisioner._units = ["arn:1"]
        self.provisioner._desired_count = 1
        with patch.object(self.provisioner, "start_units", new_callable=AsyncMock) as start_mock:
            with patch.object(self.provisioner, "stop_units", new_callable=AsyncMock) as stop_mock:
                await self.provisioner._reconcile()
                start_mock.assert_not_called()
                stop_mock.assert_not_called()

    async def test_reconcile_respects_max_instances(self) -> None:
        provisioner = _make_provisioner(max_task_concurrency=8, ecs_task_cpu=4)
        provisioner._desired_count = 5
        with patch.object(provisioner, "start_units", new_callable=AsyncMock) as start_mock:
            with patch.object(provisioner, "stop_units", new_callable=AsyncMock) as stop_mock:
                await provisioner._reconcile()
                start_mock.assert_called_once_with(2)  # max_instances=2, current=0, delta capped to 2
                stop_mock.assert_not_called()

    async def test_set_desired_task_concurrency_converts_to_instances(self) -> None:
        provisioner = _make_provisioner(ecs_task_cpu=4)
        request = _make_request(task_concurrency=10, capabilities={})
        with patch.object(provisioner, "_reconcile", new_callable=AsyncMock):
            await provisioner.set_desired_task_concurrency([request])
            await asyncio.sleep(0)
        self.assertEqual(provisioner._desired_count, 3)  # ceil(10 / 4) = 3

    async def test_set_desired_task_concurrency_triggers_reconcile(self) -> None:
        request = _make_request(task_concurrency=4, capabilities={})
        with patch.object(self.provisioner, "_reconcile", new_callable=AsyncMock) as reconcile_mock:
            await self.provisioner.set_desired_task_concurrency([request])
            self.assertIsNotNone(self.provisioner._pending_reconcile_task)
            await asyncio.sleep(0)
        reconcile_mock.assert_called_once()

    async def test_set_desired_task_concurrency_coalesces_rapid_calls(self) -> None:
        request = _make_request(task_concurrency=4, capabilities={})
        with patch.object(self.provisioner, "_reconcile", new_callable=AsyncMock) as reconcile_mock:
            await self.provisioner.set_desired_task_concurrency([request])
            await self.provisioner.set_desired_task_concurrency([request])
            await self.provisioner.set_desired_task_concurrency([request])
            await asyncio.sleep(0)
        reconcile_mock.assert_called_once()
