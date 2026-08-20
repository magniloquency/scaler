import unittest
from typing import List, Optional, cast
from unittest.mock import patch

from scaler.worker.worker import Worker
from scaler.worker_manager_adapter.baremetal.native import NativeWorkerProvisioner


class _FakeWorker:
    """Stands in for a Worker process: only the bits _reap_dead_workers touches."""

    def __init__(self, identity: bytes, alive: bool = True, exitcode: Optional[int] = None) -> None:
        self.identity = identity
        self._alive = alive
        self.exitcode = exitcode
        self.joined = False

    def is_alive(self) -> bool:
        return self._alive

    def join(self) -> None:
        self.joined = True

    def die(self, exitcode: int) -> None:
        self._alive = False
        self.exitcode = exitcode


def _make_provisioner(workers: List[_FakeWorker]) -> NativeWorkerProvisioner:
    provisioner = NativeWorkerProvisioner.__new__(NativeWorkerProvisioner)
    provisioner._workers = cast(List[Worker], list(workers))
    return provisioner


class TestNativeWorkerReaping(unittest.TestCase):
    def test_active_unit_count_ignores_a_worker_that_died(self) -> None:
        alive, dead = _FakeWorker(b"alive"), _FakeWorker(b"dead")
        provisioner = _make_provisioner([alive, dead])
        dead.die(exitcode=1)

        self.assertEqual(provisioner.active_unit_count(), 1)
        self.assertEqual(provisioner._workers, [alive])

    def test_a_reaped_worker_is_joined(self) -> None:
        dead = _FakeWorker(b"dead")
        provisioner = _make_provisioner([dead])
        dead.die(exitcode=0)

        provisioner.active_unit_count()

        self.assertTrue(dead.joined)

    def test_a_clean_exit_is_not_a_warning(self) -> None:
        dead = _FakeWorker(b"dead")
        provisioner = _make_provisioner([dead])
        dead.die(exitcode=0)

        with patch("scaler.worker_manager_adapter.baremetal.native.logger") as mock_logger:
            provisioner.active_unit_count()

        mock_logger.warning.assert_not_called()
        mock_logger.info.assert_called_once()

    def test_an_unexpected_exit_warns(self) -> None:
        dead = _FakeWorker(b"dead")
        provisioner = _make_provisioner([dead])
        dead.die(exitcode=-9)

        with patch("scaler.worker_manager_adapter.baremetal.native.logger") as mock_logger:
            provisioner.active_unit_count()

        mock_logger.warning.assert_called_once()

    def test_count_stays_correct_across_repeated_polls(self) -> None:
        alive, dead = _FakeWorker(b"alive"), _FakeWorker(b"dead")
        provisioner = _make_provisioner([alive, dead])
        dead.die(exitcode=1)

        self.assertEqual(provisioner.active_unit_count(), 1)
        self.assertEqual(provisioner.active_unit_count(), 1)
        self.assertEqual(dead.joined, True)

    def test_all_workers_alive_is_unchanged(self) -> None:
        workers = [_FakeWorker(b"a"), _FakeWorker(b"b")]
        provisioner = _make_provisioner(workers)

        self.assertEqual(provisioner.active_unit_count(), 2)
        self.assertEqual(provisioner._workers, workers)


if __name__ == "__main__":
    unittest.main()
