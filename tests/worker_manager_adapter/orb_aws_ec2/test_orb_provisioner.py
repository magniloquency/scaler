import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from scaler.utility.identifiers import WorkerID
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
        with patch.object(self.provisioner, "_start_one_worker", new_callable=AsyncMock) as start_mock:
            with patch.object(self.provisioner, "_stop_workers", new_callable=AsyncMock) as stop_mock:
                await self.provisioner._reconcile()
                self.assertEqual(start_mock.call_count, 3)
                stop_mock.assert_not_called()

    async def test_reconcile_decreases_worker_count(self) -> None:
        wid1 = WorkerID(b"w1")
        wid2 = WorkerID(b"w2")
        wid3 = WorkerID(b"w3")
        self.provisioner._workers = {wid1: "i-1", wid2: "i-2", wid3: "i-3"}
        self.provisioner._desired_count = 1
        with patch.object(self.provisioner, "_start_one_worker", new_callable=AsyncMock) as start_mock:
            with patch.object(self.provisioner, "_stop_workers", new_callable=AsyncMock) as stop_mock:
                await self.provisioner._reconcile()
                start_mock.assert_not_called()
                stop_mock.assert_called_once_with([bytes(wid1), bytes(wid2)])

    async def test_reconcile_no_change(self) -> None:
        wid = WorkerID(b"w1")
        self.provisioner._workers = {wid: "i-1"}
        self.provisioner._desired_count = 1
        with patch.object(self.provisioner, "_start_one_worker", new_callable=AsyncMock) as start_mock:
            with patch.object(self.provisioner, "_stop_workers", new_callable=AsyncMock) as stop_mock:
                await self.provisioner._reconcile()
                start_mock.assert_not_called()
                stop_mock.assert_not_called()


class TestORBWorkerProvisionerExtractDesiredCount(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.provisioner = _make_provisioner()

    def _make_request(self, task_concurrency: int, capabilities: dict) -> MagicMock:
        request = MagicMock()
        request.taskConcurrency = task_concurrency
        request.capabilities = [MagicMock(key=key, value=value) for key, value in capabilities.items()]
        return request

    def test_returns_zero_for_empty_requests(self) -> None:
        self.assertEqual(self.provisioner._extract_desired_count([]), 0)

    def test_matches_own_capabilities(self) -> None:
        request = self._make_request(task_concurrency=8, capabilities={"cpu": 4})
        self.assertEqual(self.provisioner._extract_desired_count([request]), 8)

    def test_falls_back_to_empty_capabilities(self) -> None:
        request = self._make_request(task_concurrency=5, capabilities={})
        self.assertEqual(self.provisioner._extract_desired_count([request]), 5)

    def test_prefers_matching_over_empty_fallback(self) -> None:
        fallback = self._make_request(task_concurrency=2, capabilities={})
        matching = self._make_request(task_concurrency=6, capabilities={"cpu": 4})
        self.assertEqual(self.provisioner._extract_desired_count([fallback, matching]), 6)

    def test_falls_back_to_first_when_no_match_and_no_empty(self) -> None:
        request = self._make_request(task_concurrency=3, capabilities={"gpu": 1})
        self.assertEqual(self.provisioner._extract_desired_count([request]), 3)
