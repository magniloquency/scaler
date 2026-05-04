import asyncio
import math
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from scaler.worker_manager_adapter.aws_raw.ecs import ECSWorkerProvisioner
from scaler.worker_manager_adapter.reconcile_loop import ReconcileLoop


def _make_provisioner(max_task_concurrency: int = -1, ecs_task_cpu: int = 4) -> ECSWorkerProvisioner:
    max_instances = math.ceil(max_task_concurrency / ecs_task_cpu) if max_task_concurrency != -1 else -1
    with patch("boto3.Session"):
        provisioner = ECSWorkerProvisioner.__new__(ECSWorkerProvisioner)
        provisioner._capabilities = {}
        provisioner._ecs_task_cpu = ecs_task_cpu
        provisioner._max_task_concurrency = max_task_concurrency
        provisioner._max_instances = max_instances
        provisioner._units = []
        provisioner._reconcile_loop = ReconcileLoop(
            start_units=lambda n: provisioner.start_units(n),
            stop_units=lambda n: provisioner.stop_units(n),
            active_unit_count=lambda: len(provisioner._units),
            max_unit_count=max_instances,
        )
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


class TestECSWorkerProvisionerConcurrencyConversion(unittest.IsolatedAsyncioTestCase):
    async def test_converts_task_concurrency_to_instance_count(self) -> None:
        provisioner = _make_provisioner(ecs_task_cpu=4)
        request = _make_request(task_concurrency=10, capabilities={})
        with patch.object(provisioner._reconcile_loop, "_reconcile", new_callable=AsyncMock):
            await provisioner.set_desired_task_concurrency([request])
        self.assertEqual(provisioner._reconcile_loop._desired_unit_count, 3)  # ceil(10 / 4) = 3

    async def test_rounds_up_fractional_instance_count(self) -> None:
        provisioner = _make_provisioner(ecs_task_cpu=4)
        request = _make_request(task_concurrency=5, capabilities={})
        with patch.object(provisioner._reconcile_loop, "_reconcile", new_callable=AsyncMock):
            await provisioner.set_desired_task_concurrency([request])
        self.assertEqual(provisioner._reconcile_loop._desired_unit_count, 2)  # ceil(5 / 4) = 2

    async def test_max_instances_wired_to_reconcile_loop(self) -> None:
        provisioner = _make_provisioner(max_task_concurrency=8, ecs_task_cpu=4)
        self.assertEqual(provisioner._reconcile_loop._max_unit_count, 2)  # ceil(8 / 4) = 2


class TestECSWorkerProvisionerScalingThroughReconcileLoop(unittest.IsolatedAsyncioTestCase):
    async def test_scale_up_creates_units(self) -> None:
        provisioner = _make_provisioner(ecs_task_cpu=4)

        async def fake_start_units(count: int) -> None:
            for _ in range(count):
                provisioner._units.append(f"arn:task/{len(provisioner._units)}")

        # ECS ReconcileLoop uses a lambda so patching start_units on the instance works
        with patch.object(provisioner, "start_units", new_callable=AsyncMock, side_effect=fake_start_units):
            await provisioner.set_desired_task_concurrency([_make_request(task_concurrency=8, capabilities={})])
            await asyncio.sleep(0)  # ceil(8 / 4) = 2 units
        self.assertEqual(len(provisioner._units), 2)

    async def test_scale_down_stops_units(self) -> None:
        provisioner = _make_provisioner(ecs_task_cpu=4)
        provisioner._units = ["arn:1", "arn:2", "arn:3"]
        provisioner._ecs_client.stop_task.return_value = {"failures": []}
        await provisioner.set_desired_task_concurrency([_make_request(task_concurrency=4, capabilities={})])
        await asyncio.sleep(0)  # current=3, desired=ceil(4/4)=1 → stop_units(2)
        self.assertEqual(len(provisioner._units), 1)
