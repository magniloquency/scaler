import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from scaler.worker_manager_adapter.common import extract_desired_count
from scaler.worker_manager_adapter.orb_aws_ec2.worker_manager import ORBWorkerProvisioner


def _make_provisioner() -> ORBWorkerProvisioner:
    config = MagicMock()
    config.worker_config.per_worker_capabilities.capabilities = {"cpu": 4}
    sdk = MagicMock()
    return ORBWorkerProvisioner(config=config, max_instances=-1, sdk=sdk, template_id="tmpl-123")


class TestORBWorkerProvisionerReconcile(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.provisioner = _make_provisioner()

    async def test_reconcile_increases_worker_count(self) -> None:
        self.provisioner._desired_count = 3
        with patch.object(self.provisioner, "start_units", new_callable=AsyncMock) as start_mock:
            with patch.object(self.provisioner, "stop_units", new_callable=AsyncMock) as stop_mock:
                await self.provisioner._reconcile()
                start_mock.assert_called_once_with(3)
                stop_mock.assert_not_called()

    async def test_reconcile_decreases_worker_count(self) -> None:
        self.provisioner._units = ["i-1", "i-2", "i-3"]
        self.provisioner._desired_count = 1
        with patch.object(self.provisioner, "start_units", new_callable=AsyncMock) as start_mock:
            with patch.object(self.provisioner, "stop_units", new_callable=AsyncMock) as stop_mock:
                await self.provisioner._reconcile()
                start_mock.assert_not_called()
                stop_mock.assert_called_once_with(2)

    async def test_set_desired_task_concurrency_triggers_reconcile(self) -> None:
        request = MagicMock()
        request.taskConcurrency = 3
        request.capabilities = [MagicMock(key="cpu", value=4)]

        with patch.object(self.provisioner, "_reconcile", new_callable=AsyncMock) as reconcile_mock:
            await self.provisioner.set_desired_task_concurrency([request])
            self.assertIsNotNone(self.provisioner._pending_reconcile_task)
            await asyncio.sleep(0)

        self.assertEqual(self.provisioner._desired_count, 3)
        reconcile_mock.assert_called_once()

    async def test_set_desired_task_concurrency_coalesces_rapid_calls(self) -> None:
        request = MagicMock()
        request.taskConcurrency = 5
        request.capabilities = [MagicMock(key="cpu", value=4)]

        with patch.object(self.provisioner, "_reconcile", new_callable=AsyncMock) as reconcile_mock:
            await self.provisioner.set_desired_task_concurrency([request])
            await self.provisioner.set_desired_task_concurrency([request])
            await self.provisioner.set_desired_task_concurrency([request])
            await asyncio.sleep(0)

        reconcile_mock.assert_called_once()

    async def test_reconcile_no_change(self) -> None:
        self.provisioner._units = ["i-1"]
        self.provisioner._desired_count = 1
        with patch.object(self.provisioner, "start_units", new_callable=AsyncMock) as start_mock:
            with patch.object(self.provisioner, "stop_units", new_callable=AsyncMock) as stop_mock:
                await self.provisioner._reconcile()
                start_mock.assert_not_called()
                stop_mock.assert_not_called()


class TestExtractDesiredCount(unittest.TestCase):
    OWN_CAPABILITIES = {"cpu": 4}

    def _make_request(self, task_concurrency: int, capabilities: dict) -> MagicMock:
        request = MagicMock()
        request.taskConcurrency = task_concurrency
        request.capabilities = [MagicMock(key=key, value=value) for key, value in capabilities.items()]
        return request

    def test_returns_none_for_empty_requests(self) -> None:
        self.assertIsNone(extract_desired_count([], self.OWN_CAPABILITIES))

    def test_exact_capability_match(self) -> None:
        request = self._make_request(task_concurrency=8, capabilities={"cpu": 4})
        self.assertEqual(extract_desired_count([request], self.OWN_CAPABILITIES), 8)

    def test_empty_capabilities_matches_as_wildcard(self) -> None:
        request = self._make_request(task_concurrency=5, capabilities={})
        self.assertEqual(extract_desired_count([request], self.OWN_CAPABILITIES), 5)

    def test_prefers_more_specific_over_wildcard(self) -> None:
        wildcard = self._make_request(task_concurrency=2, capabilities={})
        specific = self._make_request(task_concurrency=6, capabilities={"cpu": 4})
        self.assertEqual(extract_desired_count([wildcard, specific], self.OWN_CAPABILITIES), 6)

    def test_returns_none_when_no_request_matches(self) -> None:
        request = self._make_request(task_concurrency=3, capabilities={"gpu": 1})
        self.assertIsNone(extract_desired_count([request], self.OWN_CAPABILITIES))
