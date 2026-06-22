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
    SIGNAL_FILAMENT_UPDATE,
    SIGNAL_NEW_SPOOL,
)
from .models import Spool
from .store import SpoolStore

HEX_COLOR_NAMES = {
    "#000000": "Black",
    "#ffffff": "White",
    "#ff0000": "Red",
    "#00ff00": "Green",
    "#0000ff": "Blue",
    "#ffff00": "Yellow",
    "#ff8000": "Orange",
    "#800080": "Purple",
    "#ffc0cb": "Pink",
    "#808080": "Gray",
    "#a52a2a": "Brown",
    "#00ffff": "Cyan",
    "#c0c0c0": "Silver",
    "#ffd700": "Gold",
    "#f5f5dc": "Beige",
    "#000080": "Navy",
    "#008080": "Teal",
    "#800000": "Maroon",
    "#808000": "Olive",
    "#ff00ff": "Magenta",
}


def _color_name(hex_code: str, spool_name: str) -> str:
    """Derive a human-readable color name from hex or spool name."""
    normalized = hex_code.lower().strip()
    if normalized in HEX_COLOR_NAMES:
        return HEX_COLOR_NAMES[normalized]
    if spool_name:
        return spool_name
    return hex_code


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    store: SpoolStore = data["store"]

    entities: list[SensorEntity] = []

    entities.append(TotalConsumedSensor(store, entry))
    entities.append(LastPrintUsageSensor(store, entry))

    for spool in store.spools.values():
        entities.append(FilamentSensor(store, entry, spool.spool_id))

    async_add_entities(entities)

    @callback
    def _on_new_spool(spool_id: str) -> None:
        spool = store.get_spool(spool_id)
        if spool is None:
            return
        async_add_entities([FilamentSensor(store, entry, spool_id)])

    entry.async_on_unload(
        async_dispatcher_connect(hass, SIGNAL_NEW_SPOOL, _on_new_spool)
    )


def _tracker_device_info(entry: ConfigEntry) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, entry.data[CONF_ENTITY_PREFIX])},
        name=f"Filament Tracker ({entry.data[CONF_DEVICE_NAME]})",
        manufacturer="Bambu Lab",
        model="AMS Filament Tracker",
    )


def _filament_device_info(entry: ConfigEntry, spool: Spool) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, spool.spool_id)},
        name=f"Filament - {spool.color_hex.upper()}",
        manufacturer=spool.brand or "Unknown",
        model=spool.material_type,
        via_device=(DOMAIN, entry.data[CONF_ENTITY_PREFIX]),
    )


# ---------------------------------------------------------------------------
# Filament device sensor (one per spool — all data as attributes)
# ---------------------------------------------------------------------------


class FilamentSensor(SensorEntity):
    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_native_unit_of_measurement = UnitOfMass.GRAMS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:printer-3d-nozzle"

    def __init__(self, store: SpoolStore, entry: ConfigEntry, spool_id: str) -> None:
        self._store = store
        self._entry = entry
        self._spool_id = spool_id
        self._attr_unique_id = f"filament_{spool_id}"
        self._attr_name = "Filament"

    def _spool(self) -> Spool | None:
        return self._store.get_spool(self._spool_id)

    @property
    def device_info(self) -> DeviceInfo | None:
        spool = self._spool()
        if spool is None:
            return None
        return _filament_device_info(self._entry, spool)

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, SIGNAL_FILAMENT_UPDATE, self._handle_update
            )
        )

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()

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
            "is_loaded": spool.status == "loaded",
            "loaded_position": spool.tray_index if spool.status == "loaded" else 0,
            "remaining_capacity": round(spool.remaining_weight_g, 1),
            "start_capacity": spool.initial_weight_g,
            "type": spool.material_type,
            "color": _color_name(spool.color_hex, spool.name),
            "color_id": spool.color_hex,
            "total_consumed": round(spool.total_consumed_g, 1),
            "print_count": len(spool.print_ids),
            "spool_id": spool.spool_id,
        }


# ---------------------------------------------------------------------------
# Global stats (tracker hub device)
# ---------------------------------------------------------------------------


class TotalConsumedSensor(SensorEntity):
    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_native_unit_of_measurement = UnitOfMass.GRAMS
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_icon = "mdi:weight"

    def __init__(self, store: SpoolStore, entry: ConfigEntry) -> None:
        self._store = store
        prefix = entry.data[CONF_ENTITY_PREFIX]
        self._attr_unique_id = f"{prefix}_total_consumed"
        self._attr_name = "Total Consumed"
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

    @property
    def native_value(self) -> float:
        return round(self._store.lifetime_consumed_g, 1)


class LastPrintUsageSensor(SensorEntity):
    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_native_unit_of_measurement = UnitOfMass.GRAMS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:printer-3d-nozzle-heat"

    def __init__(self, store: SpoolStore, entry: ConfigEntry) -> None:
        self._store = store
        prefix = entry.data[CONF_ENTITY_PREFIX]
        self._attr_unique_id = f"{prefix}_last_print_usage"
        self._attr_name = "Last Print Usage"
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
