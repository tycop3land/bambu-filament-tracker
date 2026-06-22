"""Spool registry with CRUD, matching, and auto-detection."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from .const import SPOOL_STATUS_EMPTY, SPOOL_STATUS_LOADED, SPOOL_STATUS_STORED
from .models import Spool, _utcnow_iso

if TYPE_CHECKING:
    from .store import SpoolStore

_LOGGER = logging.getLogger(__name__)


class SpoolRegistry:
    """Manages spool lifecycle: creation, matching, and tray assignment."""

    def __init__(self, store: SpoolStore) -> None:
        self._store = store

    def register_spool(
        self,
        color_hex: str,
        material_type: str,
        name: str,
        brand: str = "",
        initial_weight_g: float = 1000.0,
        remaining_weight_g: float | None = None,
    ) -> Spool:
        if remaining_weight_g is None:
            remaining_weight_g = initial_weight_g
        spool = Spool(
            color_hex=color_hex,
            material_type=material_type,
            name=name,
            brand=brand,
            initial_weight_g=initial_weight_g,
            remaining_weight_g=remaining_weight_g,
            status=SPOOL_STATUS_STORED,
        )
        self._store.add_spool(spool)
        _LOGGER.info("Registered spool %s: %s %s", spool.spool_id, color_hex, name)
        return spool

    def load_spool(self, spool_id: str, tray_index: int) -> bool:
        spool = self._store.get_spool(spool_id)
        if spool is None:
            _LOGGER.warning("Spool %s not found", spool_id)
            return False
        self._store.assign_tray(spool_id, tray_index)
        spool.updated_at = _utcnow_iso()
        _LOGGER.info("Loaded spool %s into tray %d", spool_id, tray_index)
        return True

    def unload_spool(self, tray_index: int) -> Spool | None:
        spool = self._store.unassign_tray(tray_index)
        if spool:
            spool.updated_at = _utcnow_iso()
            _LOGGER.info("Unloaded spool %s from tray %d", spool.spool_id, tray_index)
        return spool

    def adjust_remaining(self, spool_id: str, remaining_weight_g: float) -> bool:
        spool = self._store.get_spool(spool_id)
        if spool is None:
            _LOGGER.warning("Spool %s not found for adjustment", spool_id)
            return False
        old = spool.remaining_weight_g
        spool.remaining_weight_g = max(0.0, remaining_weight_g)
        spool.updated_at = _utcnow_iso()
        if spool.remaining_weight_g <= 0:
            spool.status = SPOOL_STATUS_EMPTY
        elif spool.status == SPOOL_STATUS_EMPTY:
            spool.status = SPOOL_STATUS_STORED
        _LOGGER.info(
            "Adjusted spool %s remaining: %.1f -> %.1f",
            spool_id, old, spool.remaining_weight_g,
        )
        return True

    def find_matching_spool(
        self,
        color_hex: str,
        material_type: str,
        tag_uid: str | None = None,
    ) -> Spool | None:
        if tag_uid:
            for spool in self._store.spools.values():
                if (
                    spool.tag_uid == tag_uid
                    and spool.status in (SPOOL_STATUS_STORED, SPOOL_STATUS_LOADED)
                ):
                    return spool

        candidates = [
            s
            for s in self._store.spools.values()
            if s.color_hex.lower() == color_hex.lower()
            and s.material_type.lower() == material_type.lower()
            and s.status == SPOOL_STATUS_STORED
        ]
        if len(candidates) == 1:
            return candidates[0]

        return None

    def handle_tray_change(
        self,
        tray_index: int,
        color_hex: str | None,
        material_type: str | None,
        name: str | None,
        tag_uid: str | None,
        is_empty: bool,
        default_weight_g: float = 1000.0,
    ) -> Spool | None:
        """Auto-detect spool changes from Bambu tray attribute updates.

        Returns the spool now assigned to the tray (or None if empty).
        """
        if is_empty:
            self.unload_spool(tray_index)
            return None

        current_spool = self._store.get_spool_for_tray(tray_index)
        if current_spool and self._attrs_match(current_spool, color_hex, material_type, tag_uid):
            return current_spool

        self.unload_spool(tray_index)

        color_hex = color_hex or ""
        material_type = material_type or "PLA"
        name = name or ""

        matched = self.find_matching_spool(color_hex, material_type, tag_uid)
        if matched:
            self._store.assign_tray(matched.spool_id, tray_index)
            matched.tag_uid = tag_uid or matched.tag_uid
            matched.name = name or matched.name
            matched.updated_at = _utcnow_iso()
            _LOGGER.info(
                "Auto-matched spool %s to tray %d (color=%s)",
                matched.spool_id, tray_index, color_hex,
            )
            return matched

        new_spool = Spool(
            color_hex=color_hex,
            material_type=material_type,
            name=name,
            initial_weight_g=default_weight_g,
            remaining_weight_g=default_weight_g,
            status=SPOOL_STATUS_LOADED,
            tray_index=tray_index,
            tag_uid=tag_uid,
        )
        self._store.add_spool(new_spool)
        _LOGGER.info(
            "Auto-created spool %s for tray %d (color=%s, material=%s)",
            new_spool.spool_id, tray_index, color_hex, material_type,
        )
        return new_spool

    @staticmethod
    def _attrs_match(
        spool: Spool,
        color_hex: str | None,
        material_type: str | None,
        tag_uid: str | None,
    ) -> bool:
        if tag_uid and spool.tag_uid:
            return spool.tag_uid == tag_uid
        if color_hex and material_type:
            return (
                spool.color_hex.lower() == color_hex.lower()
                and spool.material_type.lower() == material_type.lower()
            )
        return False
