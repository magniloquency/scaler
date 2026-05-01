import asyncio
import unittest
from unittest.mock import AsyncMock

from scaler.worker_manager_adapter.reconcile_loop import ReconcileLoop


def _make_loop(units: list, max_unit_count: int = -1) -> tuple[ReconcileLoop, AsyncMock, AsyncMock]:
    start_mock = AsyncMock()
    stop_mock = AsyncMock()
    loop = ReconcileLoop(
        start_units=start_mock,
        stop_units=stop_mock,
        get_current_unit_count=lambda: len(units),
        max_unit_count=max_unit_count,
    )
    return loop, start_mock, stop_mock


class TestReconcileLoopReconcile(unittest.IsolatedAsyncioTestCase):
    async def test_reconcile_calls_start_when_desired_exceeds_current(self) -> None:
        loop, start_mock, stop_mock = _make_loop(units=[])
        await loop.set_desired_unit_count(3)
        await asyncio.sleep(0)
        start_mock.assert_called_once_with(3)
        stop_mock.assert_not_called()

    async def test_reconcile_calls_stop_when_current_exceeds_desired(self) -> None:
        units = [object(), object(), object()]
        loop, start_mock, stop_mock = _make_loop(units=units)
        await loop.set_desired_unit_count(1)
        await asyncio.sleep(0)
        start_mock.assert_not_called()
        stop_mock.assert_called_once_with(2)

    async def test_reconcile_noop_when_desired_equals_current(self) -> None:
        units = [object()]
        loop, start_mock, stop_mock = _make_loop(units=units)
        await loop.set_desired_unit_count(1)
        await asyncio.sleep(0)
        start_mock.assert_not_called()
        stop_mock.assert_not_called()

    async def test_reconcile_respects_max_unit_count_cap_on_upscale(self) -> None:
        loop, start_mock, stop_mock = _make_loop(units=[], max_unit_count=2)
        await loop.set_desired_unit_count(5)
        await asyncio.sleep(0)
        start_mock.assert_called_once_with(2)
        stop_mock.assert_not_called()

    async def test_reconcile_max_unit_count_does_not_cap_downscale(self) -> None:
        units = [object(), object(), object()]
        loop, start_mock, stop_mock = _make_loop(units=units, max_unit_count=2)
        await loop.set_desired_unit_count(1)
        await asyncio.sleep(0)
        start_mock.assert_not_called()
        stop_mock.assert_called_once_with(2)

    async def test_reconcile_exception_is_caught_and_task_stays_alive(self) -> None:
        start_mock = AsyncMock(side_effect=RuntimeError("boom"))
        loop = ReconcileLoop(
            start_units=start_mock, stop_units=AsyncMock(), get_current_unit_count=lambda: 0, max_unit_count=-1
        )
        await loop.set_desired_unit_count(1)
        await asyncio.sleep(0)  # exception is caught internally; must not propagate here
        self.assertIsNotNone(loop._active_reconcile_task)  # task is still alive after exception


class TestReconcileLoopSetDesiredUnitCount(unittest.IsolatedAsyncioTestCase):
    async def test_set_desired_unit_count_schedules_reconcile(self) -> None:
        loop, start_mock, _ = _make_loop(units=[])
        with unittest.mock.patch.object(loop, "_reconcile", new_callable=AsyncMock) as reconcile_mock:
            await loop.set_desired_unit_count(2)
            self.assertIsNotNone(loop._active_reconcile_task)
            await asyncio.sleep(0)
        reconcile_mock.assert_called_once()

    async def test_set_desired_unit_count_coalesces_rapid_calls(self) -> None:
        loop, _, _ = _make_loop(units=[])
        with unittest.mock.patch.object(loop, "_reconcile", new_callable=AsyncMock) as reconcile_mock:
            await loop.set_desired_unit_count(1)
            await loop.set_desired_unit_count(2)
            await loop.set_desired_unit_count(3)
            await asyncio.sleep(0)
        reconcile_mock.assert_called_once()

    async def test_set_desired_unit_count_processes_successive_signals(self) -> None:
        loop, start_mock, _ = _make_loop(units=[])
        await loop.set_desired_unit_count(1)
        await asyncio.sleep(0)  # first reconcile fires
        await loop.set_desired_unit_count(2)
        await asyncio.sleep(0)  # second reconcile fires
        self.assertEqual(start_mock.call_count, 2)

    async def test_set_desired_unit_count_noop_when_count_unchanged(self) -> None:
        loop, _, _ = _make_loop(units=[])
        with unittest.mock.patch.object(loop, "_reconcile", new_callable=AsyncMock) as reconcile_mock:
            await loop.set_desired_unit_count(0)  # already 0 — no change
            await asyncio.sleep(0)
        reconcile_mock.assert_not_called()

    async def test_cancel_stops_reconcile(self) -> None:
        loop, _, _ = _make_loop(units=[])
        await loop.set_desired_unit_count(1)
        loop.cancel()
        self.assertTrue(loop._stop.is_set())
