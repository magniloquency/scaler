import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from scaler.worker_manager_adapter.common import extract_desired_count
from scaler.worker_manager_adapter.orb_aws_ec2.worker_manager import ORBWorkerProvisioner


def _make_provisioner(workers_per_instance: int = 1, max_instances: int = -1) -> ORBWorkerProvisioner:
    config = MagicMock()
    config.worker_config.per_worker_capabilities.capabilities = {"cpu": 4}
    sdk = MagicMock()
    return ORBWorkerProvisioner(
        config=config,
        max_instances=max_instances,
        sdk=sdk,
        template_id="tmpl-123",
        workers_per_instance=workers_per_instance,
    )


def _make_request(task_concurrency: int, capabilities: dict) -> MagicMock:
    request = MagicMock()
    request.taskConcurrency = task_concurrency
    request.capabilities = [MagicMock(key=k, value=v) for k, v in capabilities.items()]
    return request


class TestORBWorkerProvisionerConcurrencyConversion(unittest.IsolatedAsyncioTestCase):
    async def test_converts_workers_to_instance_count(self) -> None:
        provisioner = _make_provisioner(workers_per_instance=16)
        request = _make_request(task_concurrency=100, capabilities={"cpu": 4})
        with patch.object(provisioner._reconcile_loop, "_reconcile", new_callable=AsyncMock):
            await provisioner.set_desired_task_concurrency([request])
        self.assertEqual(provisioner._reconcile_loop._desired_unit_count, 7)  # ceil(100 / 16) = 7

    async def test_desired_unit_count_is_zero_when_no_matching_requests(self) -> None:
        provisioner = _make_provisioner()
        with patch.object(provisioner._reconcile_loop, "_reconcile", new_callable=AsyncMock):
            await provisioner.set_desired_task_concurrency([])
        self.assertEqual(provisioner._reconcile_loop._desired_unit_count, 0)

    async def test_max_instances_wired_to_reconcile_loop(self) -> None:
        provisioner = _make_provisioner(max_instances=5)
        self.assertEqual(provisioner._reconcile_loop._max_unit_count, 5)


class TestExtractDesiredCount(unittest.TestCase):
    OWN_CAPABILITIES = {"cpu": 4}

    def _make_request(self, task_concurrency: int, capabilities: dict) -> MagicMock:
        request = MagicMock()
        request.taskConcurrency = task_concurrency
        request.capabilities = [MagicMock(key=key, value=value) for key, value in capabilities.items()]
        return request

    def test_returns_zero_for_empty_requests(self) -> None:
        self.assertEqual(extract_desired_count([], self.OWN_CAPABILITIES), 0)

    def test_exact_capability_match(self) -> None:
        request = self._make_request(task_concurrency=8, capabilities={"cpu": 4})
        self.assertEqual(extract_desired_count([request], self.OWN_CAPABILITIES), 8)

    def test_empty_capabilities_matches_as_wildcard(self) -> None:
        request = self._make_request(task_concurrency=5, capabilities={})
        self.assertEqual(extract_desired_count([request], self.OWN_CAPABILITIES), 5)

    def test_sums_all_matching_requests(self) -> None:
        wildcard = self._make_request(task_concurrency=2, capabilities={})
        specific = self._make_request(task_concurrency=6, capabilities={"cpu": 4})
        self.assertEqual(extract_desired_count([wildcard, specific], self.OWN_CAPABILITIES), 8)

    def test_returns_zero_when_no_request_matches(self) -> None:
        request = self._make_request(task_concurrency=3, capabilities={"gpu": 1})
        self.assertEqual(extract_desired_count([request], self.OWN_CAPABILITIES), 0)

    def test_sums_multiple_matches_excluding_non_matching(self) -> None:
        wildcard = self._make_request(task_concurrency=4, capabilities={})
        matching = self._make_request(task_concurrency=3, capabilities={"cpu": 4})
        non_matching = self._make_request(task_concurrency=10, capabilities={"gpu": 1})
        self.assertEqual(
            extract_desired_count([wildcard, matching, non_matching], self.OWN_CAPABILITIES),
            7,  # 4 + 3; non_matching excluded
        )
