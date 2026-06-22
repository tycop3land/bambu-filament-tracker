"""Sensor platform for Bambu Filament Tracker."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfMass
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_DEVICE_NAME,
    CONF_ENTITY_PREFIX,
    DOMAIN,
    NUM_TRAYS,
    SIGNAL_FILAMENT_UPDATE,
    SIGNAL_NEW_SPOOL,
)
from .models import Spool
from .store import SpoolStore


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    store: SpoolStore = data["store"]

    entities: list[SensorEntity] = []

    # Tracker hub: tray contents + global stats
    for tray in range(1, NUM_TRAYS + 1):
        entities.append(TrayContentSensor(store, entry, tray))
    entities.append(TotalConsumedSensor(store, entry))
    entities.append(LastPrintUsageSensor(store, entry))

    # One device per existing spool
    for spool in store.spools.values():
        entities.extend(_create_spool_sensors(store, entry, spool))

    async_add_entities(entities)

    @callback
    def _on_new_spool(spool_id: str) -> None:
        spool = store.get_spool(spool_id)
        if spool is None:
            return
        async_add_entities(_create_spool_sensors(store, entry, spool))

    entry.async_on_unload(
        async_dispatcher_connect(hass, SIGNAL_NEW_SPOOL, _on_new_spool)
    )


def _create_spool_sensors(
    store: SpoolStore, entry: ConfigEntry, spool: Spool
) -> list[SensorEntity]:
    return [
        SpoolRemainingSensor(store, entry, spool.spool_id),
        SpoolRemainingPctSensor(store, entry, spool.spool_id),
        SpoolStatusSensor(store, entry, spool.spool_id),
    ]


def _tracker_device_info(entry: ConfigEntry) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, entry.data[CONF_ENTITY_PREFIX])},
        name=f"Filament Tracker ({entry.data[CONF_DEVICE_NAME]})",
        manufacturer="Bambu Lab",
        model="AMS Filament Tracker",
    )


def _spool_device_info(entry: ConfigEntry, spool: Spool) -> DeviceInfo:
    name = spool.name or f"{spool.color_hex} {spool.material_type}"
    return DeviceInfo(
        identifiers={(DOMAIN, spool.spool_id)},
        name=name,
        manufacturer=spool.brand or "Unknown",
        model=spool.material_type,
        via_device=(DOMAIN, entry.data[CONF_ENTITY_PREFIX]),
    )


# ---------------------------------------------------------------------------
# Per-spool device sensors (PRIMARY — each spool is its own device)
# ---------------------------------------------------------------------------


class _BaseSpoolSensor(SensorEntity):
    _attr_should_poll = False
    _attr_has_entity_name = True

    def __init__(self, store: SpoolStore, entry: ConfigEntry, spool_id: str) -> None:
        self._store = store
        self._entry = entry
        self._spool_id = spool_id

    def _spool(self) -> Spool | None:
        return self._store.get_spool(self._spool_id)

    @property
    def device_info(self) -> DeviceInfo | None:
        spool = self._spool()
        if spool is None:
            return None
        return _spool_device_info(self._entry, spool)

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, SIGNAL_FILAMENT_UPDATE, self._handle_update
            )
        )

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()


class SpoolRemainingSensor(_BaseSpoolSensor):
    _attr_native_unit_of_measurement = UnitOfMass.GRAMS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:printer-3d-nozzle"

    def __init__(self, store: SpoolStore, entry: ConfigEntry, spool_id: str) -> None:
        super().__init__(store, entry, spool_id)
        self._attr_unique_id = f"spool_{spool_id}_remaining"
        self._attr_name = "Remaining"

    @property
    def native_value(self) -> float | None:
        spool = self._spool()
        return round(spool.remaining_weight_g, 1) if spool else None

    @property
    def extra_state_attributes(self) -> dict:
        spool = self._spool()
        if spool is None:
            return {}
        return {
            "color_hex": spool.color_hex,
            "material": spool.material_type,
            "initial_weight_g": spool.initial_weight_g,
            "total_consumed_g": round(spool.total_consumed_g, 1),
            "brand": spool.brand,
            "tray": spool.tray_index,
            "status": spool.status,
            "spool_id": spool.spool_id,
        }


class SpoolRemainingPctSensor(_BaseSpoolSensor):
    _attr_native_unit_of_measurement = "%"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:gauge"

    def __init__(self, store: SpoolStore, entry: ConfigEntry, spool_id: str) -> None:
        super().__init__(store, entry, spool_id)
        self._attr_unique_id = f"spool_{spool_id}_remaining_pct"
        self._attr_name = "Remaining %"

    @property
    def native_value(self) -> int | None:
        spool = self._spool()
        if spool is None or spool.initial_weight_g <= 0:
            return None
        return round(spool.remaining_weight_g / spool.initial_weight_g * 100)


class SpoolStatusSensor(_BaseSpoolSensor):
    _attr_icon = "mdi:tray-full"

    def __init__(self, store: SpoolStore, entry: ConfigEntry, spool_id: str) -> None:
        super().__init__(store, entry, spool_id)
        self._attr_unique_id = f"spool_{spool_id}_status"
        self._attr_name = "Status"

    @property
    def native_value(self) -> str | None:
        spool = self._spool()
        if spool is None:
            return None
        if spool.status == "loaded" and spool.tray_index is not None:
            return f"Loaded (Tray {spool.tray_index})"
        return spool.status.capitalize()

    @property
    def extra_state_attributes(self) -> dict:
        spool = self._spool()
        if spool is None:
            return {}
        return {
            "tray_index": spool.tray_index,
            "print_count": len(spool.print_ids),
            "created_at": spool.created_at,
        }


# ---------------------------------------------------------------------------
# Tracker hub sensors (minimal — just tray contents + global stats)
# ---------------------------------------------------------------------------


class _BaseTrackerSensor(SensorEntity):
    _attr_should_poll = False
    _attr_has_entity_name = True

    def __init__(self, store: SpoolStore, entry: ConfigEntry) -> None:
        self._store = store
        self._entry = entry
        self._attr_device_info = _tracker_device_info(entry)

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, SIGNAL_FILAMENT_UPDATE, self._handle_update
            )
        )

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()


class TrayContentSensor(_BaseTrackerSensor):
    """Shows which spool is loaded in each tray — quick reference only."""

    _attr_icon = "mdi:tray-arrow-down"

    def __init__(self, store: SpoolStore, entry: ConfigEntry, tray: int) -> None:
        super().__init__(store, entry)
        self._tray = tray
        prefix = entry.data[CONF_ENTITY_PREFIX]
        self._attr_unique_id = f"{prefix}_tray_{tray}_content"
        self._attr_name = f"Tray {tray}"

    @property
    def native_value(self) -> str | None:
        spool = self._store.get_spool_for_tray(self._tray)
        if spool is None:
            return "Empty"
        return spool.name or f"{spool.color_hex} {spool.material_type}"

    @property
    def extra_state_attributes(self) -> dict:
        spool = self._store.get_spool_for_tray(self._tray)
        if spool is None:
            return {}
        return {
            "spool_id": spool.spool_id,
            "color_hex": spool.color_hex,
            "material": spool.material_type,
            "remaining_g": round(spool.remaining_weight_g, 1),
            "remaining_pct": round(spool.remaining_weight_g / spool.initial_weight_g * 100)
            if spool.initial_weight_g > 0 else 0,
        }


class TotalConsumedSensor(_BaseTrackerSensor):
    _attr_native_unit_of_measurement = UnitOfMass.GRAMS
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_icon = "mdi:weight"

    def __init__(self, store: SpoolStore, entry: ConfigEntry) -> None:
        super().__init__(store, entry)
        prefix = entry.data[CONF_ENTITY_PREFIX]
        self._attr_unique_id = f"{prefix}_total_consumed"
        self._attr_name = "Total Consumed"

    @property
    def native_value(self) -> float:
        return round(self._store.lifetime_consumed_g, 1)


class LastPrintUsageSensor(_BaseTrackerSensor):
    _attr_native_unit_of_measurement = UnitOfMass.GRAMS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:printer-3d-nozzle-heat"

    def __init__(self, store: SpoolStore, entry: ConfigEntry) -> None:
        super().__init__(store, entry)
        prefix = entry.data[CONF_ENTITY_PREFIX]
        self._attr_unique_id = f"{prefix}_last_print_usage"
        self._attr_name = "Last Print Usage"

    @property
    def native_value(self) -> float:
        return round(self._store.last_print_usage_g, 1)

    @property
    def extra_state_attributes(self) -> dict:
        if not self._store.print_history:
            return {}
        last = self._store.print_history[-1]
        return {
            "gcode_file": last.gcode_file,
            "status": last.status,
            "tray_usage": {str(k): v for k, v in last.tray_usage.items()},
        }
