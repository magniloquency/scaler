import asyncio
import unittest
from unittest.mock import AsyncMock

from scaler.worker_manager_adapter.reconcile_loop import ReconcileLoop


def _make_loop(units: list, max_units: int = -1) -> tuple[ReconcileLoop, AsyncMock, AsyncMock]:
    start_mock = AsyncMock()
    stop_mock = AsyncMock()
    loop = ReconcileLoop(
        start_units=start_mock, stop_units=stop_mock, get_current_count=lambda: len(units), max_units=max_units
    )
    return loop, start_mock, stop_mock


class TestReconcileLoopReconcile(unittest.IsolatedAsyncioTestCase):
    async def test_reconcile_calls_start_when_desired_exceeds_current(self) -> None:
        loop, start_mock, stop_mock = _make_loop(units=[])
        loop._desired_count = 3
        await loop._reconcile()
        start_mock.assert_called_once_with(3)
        stop_mock.assert_not_called()

    async def test_reconcile_calls_stop_when_current_exceeds_desired(self) -> None:
        units = [object(), object(), object()]
        loop, start_mock, stop_mock = _make_loop(units=units)
        loop._desired_count = 1
        await loop._reconcile()
        start_mock.assert_not_called()
        stop_mock.assert_called_once_with(2)

    async def test_reconcile_noop_when_desired_equals_current(self) -> None:
        units = [object()]
        loop, start_mock, stop_mock = _make_loop(units=units)
        loop._desired_count = 1
        await loop._reconcile()
        start_mock.assert_not_called()
        stop_mock.assert_not_called()

    async def test_reconcile_respects_max_units_cap_on_upscale(self) -> None:
        loop, start_mock, stop_mock = _make_loop(units=[], max_units=2)
        loop._desired_count = 5
        await loop._reconcile()
        start_mock.assert_called_once_with(2)
        stop_mock.assert_not_called()

    async def test_reconcile_max_units_does_not_cap_downscale(self) -> None:
        units = [object(), object(), object()]
        loop, start_mock, stop_mock = _make_loop(units=units, max_units=2)
        loop._desired_count = 1
        await loop._reconcile()
        start_mock.assert_not_called()
        stop_mock.assert_called_once_with(2)

    async def test_reconcile_exception_is_caught_and_does_not_propagate(self) -> None:
        start_mock = AsyncMock(side_effect=RuntimeError("boom"))
        loop = ReconcileLoop(start_units=start_mock, stop_units=AsyncMock(), get_current_count=lambda: 0)
        loop._desired_count = 1
        await loop._reconcile()  # must not raise

    async def test_reconcile_clears_active_task_on_exception(self) -> None:
        start_mock = AsyncMock(side_effect=RuntimeError("boom"))
        loop = ReconcileLoop(start_units=start_mock, stop_units=AsyncMock(), get_current_count=lambda: 0)
        loop._desired_count = 1
        await loop._reconcile()
        self.assertIsNone(loop._active_reconcile_task)


class TestReconcileLoopSetDesired(unittest.IsolatedAsyncioTestCase):
    async def test_set_desired_schedules_reconcile(self) -> None:
        loop, start_mock, _ = _make_loop(units=[])
        with unittest.mock.patch.object(loop, "_reconcile", new_callable=AsyncMock) as reconcile_mock:
            await loop.set_desired(2)
            self.assertIsNotNone(loop._pending_reconcile_task)
            await asyncio.sleep(0)
        reconcile_mock.assert_called_once()

    async def test_set_desired_coalesces_rapid_calls(self) -> None:
        loop, _, _ = _make_loop(units=[])
        with unittest.mock.patch.object(loop, "_reconcile", new_callable=AsyncMock) as reconcile_mock:
            await loop.set_desired(1)
            await loop.set_desired(2)
            await loop.set_desired(3)
            await asyncio.sleep(0)
        reconcile_mock.assert_called_once()

    async def test_set_desired_allows_new_reconcile_after_previous_completes(self) -> None:
        loop, start_mock, _ = _make_loop(units=[])
        await loop.set_desired(1)
        await asyncio.sleep(0)  # first reconcile runs and clears _pending_reconcile_task
        self.assertIsNone(loop._pending_reconcile_task)
        await loop.set_desired(2)
        await asyncio.sleep(0)
        self.assertEqual(start_mock.call_count, 2)

    async def test_set_desired_zero_does_not_schedule_when_already_zero(self) -> None:
        loop, _, _ = _make_loop(units=[])
        with unittest.mock.patch.object(loop, "_reconcile", new_callable=AsyncMock) as reconcile_mock:
            await loop.set_desired(0)
            await asyncio.sleep(0)
        reconcile_mock.assert_called_once()
