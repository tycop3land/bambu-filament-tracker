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

COLOR_TABLE: list[tuple[int, int, int, str]] = [
    (0, 0, 0, "Black"),
    (32, 32, 32, "Dark Gray"),
    (64, 64, 64, "Charcoal"),
    (128, 128, 128, "Gray"),
    (192, 192, 192, "Silver"),
    (245, 245, 245, "Off White"),
    (255, 255, 255, "White"),
    (255, 0, 0, "Red"),
    (178, 34, 34, "Crimson"),
    (128, 0, 0, "Maroon"),
    (255, 69, 0, "Red Orange"),
    (255, 99, 71, "Tomato"),
    (255, 127, 80, "Coral"),
    (255, 128, 0, "Orange"),
    (255, 165, 0, "Bright Orange"),
    (255, 215, 0, "Gold"),
    (255, 255, 0, "Yellow"),
    (255, 228, 196, "Bisque"),
    (245, 245, 220, "Beige"),
    (240, 230, 140, "Khaki"),
    (128, 128, 0, "Olive"),
    (0, 100, 0, "Dark Green"),
    (0, 128, 0, "Green"),
    (0, 176, 80, "Emerald"),
    (34, 139, 34, "Forest Green"),
    (0, 255, 0, "Lime"),
    (144, 238, 144, "Light Green"),
    (0, 128, 128, "Teal"),
    (0, 206, 209, "Turquoise"),
    (0, 255, 255, "Cyan"),
    (0, 191, 255, "Sky Blue"),
    (70, 130, 180, "Steel Blue"),
    (0, 0, 255, "Blue"),
    (0, 0, 128, "Navy"),
    (75, 0, 130, "Indigo"),
    (128, 0, 128, "Purple"),
    (148, 103, 189, "Violet"),
    (230, 230, 250, "Lavender"),
    (255, 0, 255, "Magenta"),
    (255, 105, 180, "Hot Pink"),
    (255, 192, 203, "Pink"),
    (165, 42, 42, "Brown"),
    (139, 90, 43, "Tan"),
]


def _hex_to_rgb(hex_code: str) -> tuple[int, int, int]:
    h = hex_code.lstrip("#")
    if len(h) >= 8:
        h = h[:6]
    elif len(h) < 6:
        h = h.ljust(6, "0")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _color_name(hex_code: str, spool_name: str) -> str:
    """Find the closest named color by Euclidean distance in RGB space."""
    try:
        r, g, b = _hex_to_rgb(hex_code)
    except (ValueError, IndexError):
        return spool_name or hex_code

    best_name = spool_name or hex_code
    best_dist = float("inf")
    for cr, cg, cb, name in COLOR_TABLE:
        dist = (r - cr) ** 2 + (g - cg) ** 2 + (b - cb) ** 2
        if dist < best_dist:
            best_dist = dist
            best_name = name
    return best_name


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


def _filament_device_name(spool: Spool) -> str:
    color = _color_name(spool.color_hex, "")
    name = spool.name or spool.material_type
    return f"Filament - {name} - {color} ({spool.color_hex.upper()})"


def _filament_device_info(entry: ConfigEntry, spool: Spool) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, spool.spool_id)},
        name=_filament_device_name(spool),
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
        remaining_pct = (
            round(spool.remaining_weight_g / spool.initial_weight_g * 100, 1)
            if spool.initial_weight_g > 0
            else 0
        )
        return {
            "is_loaded": spool.status == "loaded",
            "loaded_position": spool.tray_index if spool.status == "loaded" else 0,
            "remaining_capacity": round(spool.remaining_weight_g, 1),
            "remaining_pct": remaining_pct,
            "start_capacity": spool.initial_weight_g,
            "type": spool.material_type,
            "color": _color_name(spool.color_hex, spool.name),
            "color_id": spool.color_hex,
            "brand": spool.brand or "Unknown",
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
