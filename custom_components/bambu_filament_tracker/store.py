"""Persistent storage for Bambu Filament Tracker."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.helpers.storage import Store

from .const import STORAGE_KEY, STORAGE_VERSION
from .models import PrintRecord, Spool, TrackerState

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


class SpoolStore:
    """Manages persistent storage for spools, prints, and tracker state."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        self._store = Store(hass, STORAGE_VERSION, f"{STORAGE_KEY}.{entry_id}")
        self.spools: dict[str, Spool] = {}
        self.tray_assignments: dict[int, str | None] = {1: None, 2: None, 3: None, 4: None}
        self.print_history: list[PrintRecord] = []
        self.tracker_state: TrackerState = TrackerState()
        self.lifetime_consumed_g: float = 0.0
        self.last_print_usage_g: float = 0.0

    async def async_load(self) -> None:
        data = await self._store.async_load()
        if data is None:
            return

        for spool_data in data.get("spools", {}).values():
            spool = Spool.from_dict(spool_data)
            self.spools[spool.spool_id] = spool

        for key, val in data.get("tray_assignments", {}).items():
            self.tray_assignments[int(key)] = val

        for record_data in data.get("print_history", []):
            self.print_history.append(PrintRecord.from_dict(record_data))

        ts_data = data.get("tracker_state")
        if ts_data:
            self.tracker_state = TrackerState.from_dict(ts_data)

        self.lifetime_consumed_g = data.get("lifetime_consumed_g", 0.0)
        self.last_print_usage_g = data.get("last_print_usage_g", 0.0)

    async def async_save(self) -> None:
        data = {
            "spools": {sid: s.to_dict() for sid, s in self.spools.items()},
            "tray_assignments": {str(k): v for k, v in self.tray_assignments.items()},
            "print_history": [r.to_dict() for r in self.print_history],
            "tracker_state": self.tracker_state.to_dict(),
            "lifetime_consumed_g": self.lifetime_consumed_g,
            "last_print_usage_g": self.last_print_usage_g,
        }
        await self._store.async_save(data)

    def get_spool(self, spool_id: str) -> Spool | None:
        return self.spools.get(spool_id)

    def get_spool_for_tray(self, tray_index: int) -> Spool | None:
        spool_id = self.tray_assignments.get(tray_index)
        if spool_id is None:
            return None
        return self.spools.get(spool_id)

    def add_spool(self, spool: Spool) -> None:
        self.spools[spool.spool_id] = spool
        if spool.tray_index is not None:
            self.tray_assignments[spool.tray_index] = spool.spool_id

    def assign_tray(self, spool_id: str, tray_index: int) -> None:
        spool = self.spools.get(spool_id)
        if spool is None:
            return
        existing_id = self.tray_assignments.get(tray_index)
        if existing_id and existing_id != spool_id:
            existing = self.spools.get(existing_id)
            if existing:
                existing.status = "stored"
                existing.tray_index = None
        spool.tray_index = tray_index
        spool.status = "loaded"
        self.tray_assignments[tray_index] = spool_id

    def unassign_tray(self, tray_index: int) -> Spool | None:
        spool_id = self.tray_assignments.get(tray_index)
        if spool_id is None:
            return None
        spool = self.spools.get(spool_id)
        if spool:
            spool.status = "stored"
            spool.tray_index = None
        self.tray_assignments[tray_index] = None
        return spool

    def add_print_record(self, record: PrintRecord) -> None:
        self.print_history.append(record)
        for tray_idx in record.tray_usage:
            spool_id = self.tray_assignments.get(tray_idx)
            if spool_id:
                spool = self.spools.get(spool_id)
                if spool:
                    spool.print_ids.append(record.record_id)
