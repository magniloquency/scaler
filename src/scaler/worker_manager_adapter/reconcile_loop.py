from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable, Optional


class ReconcileLoop:
    def __init__(
        self,
        start_units: Callable[[int], Awaitable[None]],
        stop_units: Callable[[int], Awaitable[None]],
        get_current_count: Callable[[], int],
        max_units: int = -1,
    ) -> None:
        self._start_units = start_units
        self._stop_units = stop_units
        self._get_current_count = get_current_count
        self._max_units = max_units
        self._desired_count: int = 0
        self._reconcile_lock: asyncio.Lock = asyncio.Lock()
        self._pending_reconcile_task: Optional[asyncio.Task] = None
        self._active_reconcile_task: Optional[asyncio.Task] = None

    async def set_desired(self, count: int) -> None:
        if count != self._desired_count:
            logging.info(f"Desired unit count changed: {self._desired_count} → {count}")
        self._desired_count = count
        if self._pending_reconcile_task is None:
            self._pending_reconcile_task = asyncio.create_task(self._reconcile())

    async def _reconcile(self) -> None:
        async with self._reconcile_lock:
            self._active_reconcile_task = asyncio.current_task()
            self._pending_reconcile_task = None
            try:
                current = self._get_current_count()
                delta = self._desired_count - current
                if self._max_units != -1:
                    delta = min(delta, self._max_units - current)
                capped = self._max_units != -1 and delta != self._desired_count - current
                msg = f"Reconcile: desired={self._desired_count}, current={current}, delta={delta:+d}" + (
                    f" (capped by max_units={self._max_units})" if capped else ""
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
