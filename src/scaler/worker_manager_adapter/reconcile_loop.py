from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable, Optional


class ReconcileLoop:
    """Manages async scale-up/down reconciliation for a pool of homogeneous units.

    Callers set a desired unit count via `set_desired_unit_count`. The loop
    compares that against the live count returned by `get_current_unit_count` and
    calls `start_units` or `stop_units` with the delta. Rapid successive calls to
    `set_desired_unit_count` are coalesced: at most one reconcile runs at a time,
    and a second call while one is in-flight schedules exactly one follow-up.

    Args:
        start_units: Async callable that launches `n` new units.
        stop_units: Async callable that terminates `n` existing units.
        get_current_unit_count: Callable that returns the current live unit count.
        max_unit_count: Hard cap on the number of units. -1 means unlimited.
    """

    def __init__(
        self,
        start_units: Callable[[int], Awaitable[None]],
        stop_units: Callable[[int], Awaitable[None]],
        get_current_unit_count: Callable[[], int],
        max_unit_count: int = -1,
    ) -> None:
        self._start_units = start_units
        self._stop_units = stop_units
        self._get_current_unit_count = get_current_unit_count
        self._max_unit_count = max_unit_count
        self._desired_unit_count: int = 0
        self._reconcile_lock: asyncio.Lock = asyncio.Lock()
        self._pending_reconcile_task: Optional[asyncio.Task] = None
        self._active_reconcile_task: Optional[asyncio.Task] = None

    async def set_desired_unit_count(self, count: int) -> None:
        """Set the desired number of units and schedule a reconcile if needed."""
        if count != self._desired_unit_count:
            logging.info(f"Desired unit count changed: {self._desired_unit_count} → {count}")
        self._desired_unit_count = count
        if self._pending_reconcile_task is None:
            self._pending_reconcile_task = asyncio.create_task(self._reconcile())

    async def _reconcile(self) -> None:
        async with self._reconcile_lock:
            self._active_reconcile_task = asyncio.current_task()
            self._pending_reconcile_task = None
            try:
                current = self._get_current_unit_count()
                delta = self._desired_unit_count - current
                if self._max_unit_count != -1:
                    delta = min(delta, self._max_unit_count - current)
                capped = self._max_unit_count != -1 and delta != self._desired_unit_count - current
                msg = f"Reconcile: desired={self._desired_unit_count}, current={current}, delta={delta:+d}" + (
                    f" (capped by max_unit_count={self._max_unit_count})" if capped else ""
                )
                if delta != 0:
                    logging.info(msg)
                else:
                    logging.debug(msg)
                if delta > 0:
                    await self._start_units(delta)
                elif delta < 0:
                    await self._stop_units(abs(delta))
            except Exception as exc:
                logging.exception(f"Reconcile failed: {exc}")
            finally:
                self._active_reconcile_task = None
