"""Consumption tracking state machine for Bambu Filament Tracker."""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_interval,
)

from .const import (
    CONF_ENTITY_PREFIX,
    CONF_TARGET_AMS,
    NUM_TRAYS,
    PHASE_IDLE,
    PHASE_INTERRUPTED,
    PHASE_PRINT_COMPLETING,
    PHASE_PRINT_STARTING,
    PHASE_PRINTING,
    PHASE_RECOVERING,
    PRINT_STATUS_CANCELLED,
    PRINT_STATUS_COMPLETED,
    PRINT_STATUS_FAILED,
    PRINT_STATUS_UNTRACKED,
    SIGNAL_FILAMENT_UPDATE,
)
from .models import PrintRecord, TrackerState, _utcnow_iso

if TYPE_CHECKING:
    from datetime import timedelta

    from homeassistant.config_entries import ConfigEntry

    from .spool_registry import SpoolRegistry
    from .store import SpoolStore

_LOGGER = logging.getLogger(__name__)

PERSIST_INTERVAL_SECONDS = 60

AMS_TRAY_PATTERN = re.compile(r"AMS (\d+) Tray (\d+)")


class ConsumptionTracker:
    """Monitors Bambu printer state and tracks per-tray filament consumption."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        store: SpoolStore,
        registry: SpoolRegistry,
    ) -> None:
        self._hass = hass
        self._entry = entry
        self._store = store
        self._registry = registry
        self._prefix = entry.data[CONF_ENTITY_PREFIX]
        self._target_ams = entry.data.get(CONF_TARGET_AMS, 1)
        self._unsub: list = []
        self._pending_tray_changes: list[dict] = []

    @property
    def _state(self) -> TrackerState:
        return self._store.tracker_state

    def _entity_id(self, suffix: str) -> str:
        return f"sensor.{self._prefix}_{suffix}"

    def _binary_entity_id(self, suffix: str) -> str:
        return f"binary_sensor.{self._prefix}_{suffix}"

    def _get_state_value(self, entity_id: str) -> str | None:
        state = self._hass.states.get(entity_id)
        if state is None or state.state in ("unavailable", "unknown"):
            return None
        return state.state

    def _get_state_attr(self, entity_id: str, attr: str):
        state = self._hass.states.get(entity_id)
        if state is None:
            return None
        return state.attributes.get(attr)

    async def async_start(self) -> None:
        """Start tracking. Subscribe to state changes and sync current tray state."""
        print_status_id = self._entity_id("print_status")
        online_id = self._binary_entity_id("online")
        print_weight_id = self._entity_id("print_weight")

        _LOGGER.info(
            "Starting tracker with prefix=%s, listening to: %s, %s, %s",
            self._prefix, print_status_id, online_id, print_weight_id,
        )

        tray_ids = [self._entity_id(f"ams_{self._target_ams}_tray_{i}") for i in range(1, NUM_TRAYS + 1)]
        _LOGGER.info("Tray entity IDs: %s", tray_ids)

        # Verify entities exist
        for eid in [print_status_id, online_id, print_weight_id] + tray_ids:
            state = self._hass.states.get(eid)
            if state is None:
                _LOGGER.warning("Entity %s not found — check entity_prefix config", eid)
            else:
                _LOGGER.debug("Found entity %s = %s", eid, state.state)

        self._unsub.append(
            async_track_state_change_event(
                self._hass, [print_status_id], self._on_print_status_change
            )
        )
        self._unsub.append(
            async_track_state_change_event(
                self._hass, [online_id], self._on_online_change
            )
        )
        self._unsub.append(
            async_track_state_change_event(
                self._hass, [print_weight_id], self._on_print_weight_change
            )
        )

        self._unsub.append(
            async_track_state_change_event(
                self._hass, tray_ids, self._on_tray_change
            )
        )

        from datetime import timedelta

        self._unsub.append(
            async_track_time_interval(
                self._hass, self._periodic_persist, timedelta(seconds=PERSIST_INTERVAL_SECONDS)
            )
        )

        # Initial sync: read current tray states and create spool devices
        await self._initial_tray_sync()

        if self._state.phase in (PHASE_PRINTING, PHASE_INTERRUPTED):
            _LOGGER.info("Recovering from phase %s after restart", self._state.phase)
            self._state.phase = PHASE_RECOVERING
            await self._handle_recovery()

    async def async_stop(self) -> None:
        for unsub in self._unsub:
            unsub()
        self._unsub.clear()

    @callback
    def _on_print_status_change(self, event: Event) -> None:
        new_state = event.data.get("new_state")
        old_state = event.data.get("old_state")
        if new_state is None:
            return
        new_val = new_state.state
        old_val = old_state.state if old_state else None

        self._hass.async_create_task(
            self._handle_print_status(old_val, new_val)
        )

    @callback
    def _on_online_change(self, event: Event) -> None:
        new_state = event.data.get("new_state")
        if new_state is None:
            return
        is_online = new_state.state == "on"

        if not is_online and self._state.phase == PHASE_PRINTING:
            _LOGGER.warning("Printer went offline during print — entering INTERRUPTED")
            self._state.phase = PHASE_INTERRUPTED
            self._hass.async_create_task(self._store.async_save())
        elif is_online and self._state.phase in (PHASE_INTERRUPTED, PHASE_RECOVERING):
            _LOGGER.info("Printer back online — recovering")
            self._state.phase = PHASE_RECOVERING
            self._hass.async_create_task(self._handle_recovery())

    @callback
    def _on_print_weight_change(self, event: Event) -> None:
        if self._state.phase == PHASE_PRINT_STARTING:
            new_state = event.data.get("new_state")
            if new_state and new_state.state not in ("unavailable", "unknown", "0"):
                self._hass.async_create_task(
                    self._transition_to_printing()
                )

    @callback
    def _on_tray_change(self, event: Event) -> None:
        if self._state.phase in (PHASE_PRINTING, PHASE_PRINT_STARTING, PHASE_PRINT_COMPLETING):
            entity_id = event.data.get("entity_id", "")
            new_state = event.data.get("new_state")
            if new_state:
                self._pending_tray_changes.append({
                    "entity_id": entity_id,
                    "state": new_state,
                })
            return

        new_state = event.data.get("new_state")
        if new_state is None:
            return
        entity_id = event.data.get("entity_id", "")
        self._hass.async_create_task(
            self._process_tray_change(entity_id, new_state)
        )

    async def _periodic_persist(self, _now=None) -> None:
        if self._state.phase == PHASE_PRINTING:
            progress = self._entity_id("print_progress")
            pct = self._get_state_value(progress)
            if pct is not None:
                try:
                    self._state.print_percentage = int(float(pct))
                except (ValueError, TypeError):
                    pass
            await self._store.async_save()

    async def _handle_print_status(self, old_val: str | None, new_val: str) -> None:
        phase = self._state.phase

        if phase == PHASE_IDLE and new_val in ("prepare", "running"):
            await self._transition_to_starting()
        elif phase == PHASE_PRINT_STARTING and new_val == "running":
            await self._transition_to_printing()
        elif phase in (PHASE_PRINTING, PHASE_PRINT_STARTING) and new_val in ("finish", "failed", "idle"):
            final_status = "finish" if new_val == "finish" else new_val
            await self._transition_to_completing(final_status)
        elif phase == PHASE_RECOVERING:
            await self._handle_recovery()

    async def _transition_to_starting(self) -> None:
        _LOGGER.info("Print starting — snapshotting tray state")
        self._state.phase = PHASE_PRINT_STARTING
        self._state.print_start_time = _utcnow_iso()
        self._state.print_percentage = 0
        self._state.last_print_weight = 0.0

        gcode = self._get_state_attr(self._entity_id("print_status"), "gcode_file")
        if not gcode:
            gcode = self._get_state_attr(self._entity_id("print_status"), "subtask_name")
        self._state.gcode_file = gcode or "unknown"

        self._state.pre_print_remaining = {}
        for tray_idx in range(1, NUM_TRAYS + 1):
            spool = self._store.get_spool_for_tray(tray_idx)
            if spool:
                self._state.pre_print_remaining[tray_idx] = spool.remaining_weight_g

        self._pending_tray_changes.clear()
        await self._store.async_save()

    async def _transition_to_printing(self) -> None:
        if self._state.phase not in (PHASE_PRINT_STARTING, PHASE_RECOVERING):
            return
        _LOGGER.info("Print actively running")
        self._state.phase = PHASE_PRINTING
        await self._store.async_save()

    async def _transition_to_completing(self, final_status: str) -> None:
        _LOGGER.info("Print completing with status: %s", final_status)
        self._state.phase = PHASE_PRINT_COMPLETING

        progress = self._get_state_value(self._entity_id("print_progress"))
        if progress is not None:
            try:
                self._state.print_percentage = int(float(progress))
            except (ValueError, TypeError):
                pass

        await self._calculate_and_deduct(final_status)

        self._state.reset()
        await self._store.async_save()
        async_dispatcher_send(self._hass, SIGNAL_FILAMENT_UPDATE)

        await self._process_pending_tray_changes()

    async def _handle_recovery(self) -> None:
        print_status = self._get_state_value(self._entity_id("print_status"))
        _LOGGER.info("Recovery: print_status = %s", print_status)

        if print_status == "running":
            await self._transition_to_printing()
        elif print_status in ("finish", "failed", "idle", None):
            final = "finish" if print_status == "finish" else (print_status or "failed")
            await self._transition_to_completing(final)

    async def _calculate_and_deduct(self, final_status: str) -> None:
        weights_attr = self._get_state_attr(
            self._entity_id("print_weight"), "weights"
        )

        tray_weights = self._map_weights_to_tray_indices(weights_attr) if weights_attr else {}

        if not tray_weights:
            tray_weights = self._fallback_weight_calculation()

        if final_status == "finish":
            scale_factor = 1.0
        elif final_status == "idle":
            pct = self._state.print_percentage
            scale_factor = max(0, min(100, pct)) / 100.0 if pct > 0 else 0.0
        else:
            pct = self._state.print_percentage
            scale_factor = max(0, min(100, pct)) / 100.0 if pct > 0 else 0.0

        tray_usage: dict[int, float] = {}
        for tray_idx, planned_weight in tray_weights.items():
            consumed = round(planned_weight * scale_factor, 2)
            if consumed <= 0:
                continue
            tray_usage[tray_idx] = consumed

            spool = self._store.get_spool_for_tray(tray_idx)
            if spool:
                spool.remaining_weight_g = max(0.0, spool.remaining_weight_g - consumed)
                spool.total_consumed_g += consumed
                spool.updated_at = _utcnow_iso()
                if spool.remaining_weight_g <= 0:
                    spool.status = "empty"
                    _LOGGER.warning(
                        "Spool %s in tray %d is now empty", spool.spool_id, tray_idx
                    )

        total_consumed = sum(tray_usage.values())

        if tray_usage:
            record_status = PRINT_STATUS_COMPLETED if final_status == "finish" else (
                PRINT_STATUS_FAILED if final_status == "failed" else PRINT_STATUS_CANCELLED
            )
        else:
            record_status = PRINT_STATUS_UNTRACKED

        duration = None
        if self._state.print_start_time:
            from datetime import datetime, timezone
            try:
                start = datetime.fromisoformat(self._state.print_start_time)
                duration = int((datetime.now(timezone.utc) - start).total_seconds())
            except (ValueError, TypeError):
                pass

        record = PrintRecord(
            timestamp=_utcnow_iso(),
            gcode_file=self._state.gcode_file or "unknown",
            status=record_status,
            print_percentage=self._state.print_percentage,
            total_weight_g=total_consumed,
            tray_usage=tray_usage,
            duration_seconds=duration,
        )
        self._store.add_print_record(record)
        self._store.lifetime_consumed_g += total_consumed
        self._store.last_print_usage_g = total_consumed

        _LOGGER.info(
            "Print %s: consumed %.1fg across %d trays (status=%s, scale=%.0f%%)",
            record.record_id,
            total_consumed,
            len(tray_usage),
            record_status,
            scale_factor * 100,
        )
        for tray_idx, grams in tray_usage.items():
            _LOGGER.info("  Tray %d: %.1fg", tray_idx, grams)

    def _map_weights_to_tray_indices(self, weights: dict) -> dict[int, float]:
        result: dict[int, float] = {}
        if not isinstance(weights, dict):
            return result
        for key, weight in weights.items():
            if not isinstance(weight, (int, float)):
                continue
            match = AMS_TRAY_PATTERN.match(str(key))
            if match:
                ams_num = int(match.group(1))
                tray_num = int(match.group(2))
                if ams_num == self._target_ams:
                    result[tray_num] = float(weight)
        return result

    def _fallback_weight_calculation(self) -> dict[int, float]:
        """Fallback when weights attribute is unavailable."""
        print_weight_str = self._get_state_value(self._entity_id("print_weight"))
        if print_weight_str is None:
            _LOGGER.warning("No print weight available — print will be untracked")
            return {}

        try:
            total_weight = float(print_weight_str)
        except (ValueError, TypeError):
            _LOGGER.warning("Invalid print weight value: %s", print_weight_str)
            return {}

        loaded_trays = [
            idx for idx in range(1, NUM_TRAYS + 1)
            if self._store.get_spool_for_tray(idx) is not None
        ]

        if len(loaded_trays) == 1:
            return {loaded_trays[0]: total_weight}

        active_tray_str = self._get_state_value(self._entity_id("active_tray_index"))
        if active_tray_str is not None:
            try:
                active_idx = int(active_tray_str)
                if active_idx in loaded_trays:
                    return {active_idx: total_weight}
            except (ValueError, TypeError):
                pass

        _LOGGER.warning(
            "Multiple trays loaded but no weights attribute and no clear active tray — untracked"
        )
        return {}

    async def _initial_tray_sync(self) -> None:
        """Read current tray states on startup and create spool devices for loaded trays."""
        synced = 0
        for tray_idx in range(1, NUM_TRAYS + 1):
            entity_id = self._entity_id(f"ams_{self._target_ams}_tray_{tray_idx}")
            state = self._hass.states.get(entity_id)
            if state is None or state.state in ("unavailable", "unknown"):
                _LOGGER.debug("Tray %d: entity %s not available, skipping", tray_idx, entity_id)
                continue

            existing = self._store.get_spool_for_tray(tray_idx)
            if existing:
                _LOGGER.debug("Tray %d: already has spool %s assigned", tray_idx, existing.spool_id)
                continue

            attrs = state.attributes
            _LOGGER.info(
                "Tray %d initial sync: entity=%s, attrs=%s",
                tray_idx, entity_id, {k: v for k, v in attrs.items() if k in (
                    "color", "type", "name", "tag_uid", "empty", "remain",
                    "nozzle_temp_min", "nozzle_temp_max", "k_value",
                )},
            )

            await self._process_tray_change(entity_id, state)
            synced += 1

        if synced > 0:
            _LOGGER.info("Initial sync: created/matched %d spool(s) from tray data", synced)
        else:
            _LOGGER.info("Initial sync: no new spools to create (store has %d spools)", len(self._store.spools))

    async def _process_tray_change(self, entity_id: str, state) -> None:
        tray_match = re.search(r"tray_(\d+)$", entity_id)
        if not tray_match:
            _LOGGER.warning("Could not parse tray index from entity_id: %s", entity_id)
            return
        tray_index = int(tray_match.group(1))

        attrs = state.attributes
        color_hex = attrs.get("color")
        material_type = attrs.get("type")
        name = attrs.get("name")
        tag_uid = attrs.get("tag_uid")
        is_empty = attrs.get("empty", False)

        if isinstance(is_empty, str):
            is_empty = is_empty.lower() in ("true", "yes", "1")

        _LOGGER.debug(
            "Processing tray %d change: color=%s, type=%s, name=%s, tag_uid=%s, empty=%s",
            tray_index, color_hex, material_type, name, tag_uid, is_empty,
        )

        default_weight = self._entry.data.get("default_spool_weight_g", 1000)
        self._registry.handle_tray_change(
            tray_index=tray_index,
            color_hex=color_hex,
            material_type=material_type,
            name=name,
            tag_uid=tag_uid,
            is_empty=is_empty,
            default_weight_g=default_weight,
        )
        await self._store.async_save()
        async_dispatcher_send(self._hass, SIGNAL_FILAMENT_UPDATE)

    async def _process_pending_tray_changes(self) -> None:
        pending = list(self._pending_tray_changes)
        self._pending_tray_changes.clear()
        for change in pending:
            await self._process_tray_change(change["entity_id"], change["state"])
