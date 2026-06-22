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
)
from .store import SpoolStore


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    store: SpoolStore = data["store"]

    entities: list[SensorEntity] = []
    for tray in range(1, NUM_TRAYS + 1):
        entities.append(TrayRemainingSensor(store, entry, tray))
        entities.append(TrayRemainingPctSensor(store, entry, tray))
        entities.append(TrayColorSensor(store, entry, tray))
        entities.append(TrayMaterialSensor(store, entry, tray))

    entities.append(TotalConsumedSensor(store, entry))
    entities.append(LastPrintUsageSensor(store, entry))

    async_add_entities(entities)


def _device_info(entry: ConfigEntry) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, entry.data[CONF_ENTITY_PREFIX])},
        name=f"Filament Tracker ({entry.data[CONF_DEVICE_NAME]})",
        manufacturer="Bambu Lab",
        model="AMS Filament Tracker",
    )


class _BaseFilamentSensor(SensorEntity):
    _attr_should_poll = False
    _attr_has_entity_name = True

    def __init__(self, store: SpoolStore, entry: ConfigEntry) -> None:
        self._store = store
        self._entry = entry
        self._attr_device_info = _device_info(entry)

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, SIGNAL_FILAMENT_UPDATE, self._handle_update
            )
        )

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()


class TrayRemainingSensor(_BaseFilamentSensor):
    _attr_native_unit_of_measurement = UnitOfMass.GRAMS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:printer-3d-nozzle"

    def __init__(self, store: SpoolStore, entry: ConfigEntry, tray: int) -> None:
        super().__init__(store, entry)
        self._tray = tray
        prefix = entry.data[CONF_ENTITY_PREFIX]
        self._attr_unique_id = f"{prefix}_tray_{tray}_remaining"
        self._attr_name = f"Tray {tray} Remaining"

    @property
    def native_value(self) -> float | None:
        spool = self._store.get_spool_for_tray(self._tray)
        return round(spool.remaining_weight_g, 1) if spool else None

    @property
    def extra_state_attributes(self) -> dict:
        spool = self._store.get_spool_for_tray(self._tray)
        if spool is None:
            return {"spool_id": None, "spool_name": None, "initial_weight_g": None}
        return {
            "spool_id": spool.spool_id,
            "spool_name": spool.name,
            "initial_weight_g": spool.initial_weight_g,
            "total_consumed_g": spool.total_consumed_g,
        }


class TrayRemainingPctSensor(_BaseFilamentSensor):
    _attr_native_unit_of_measurement = "%"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:gauge"

    def __init__(self, store: SpoolStore, entry: ConfigEntry, tray: int) -> None:
        super().__init__(store, entry)
        self._tray = tray
        prefix = entry.data[CONF_ENTITY_PREFIX]
        self._attr_unique_id = f"{prefix}_tray_{tray}_remaining_pct"
        self._attr_name = f"Tray {tray} Remaining %"

    @property
    def native_value(self) -> int | None:
        spool = self._store.get_spool_for_tray(self._tray)
        if spool is None or spool.initial_weight_g <= 0:
            return None
        return round(spool.remaining_weight_g / spool.initial_weight_g * 100)

    @property
    def extra_state_attributes(self) -> dict:
        spool = self._store.get_spool_for_tray(self._tray)
        threshold = self._entry.data.get("low_threshold_pct", 10)
        return {
            "spool_id": spool.spool_id if spool else None,
            "threshold": threshold,
        }


class TrayColorSensor(_BaseFilamentSensor):
    _attr_icon = "mdi:palette"

    def __init__(self, store: SpoolStore, entry: ConfigEntry, tray: int) -> None:
        super().__init__(store, entry)
        self._tray = tray
        prefix = entry.data[CONF_ENTITY_PREFIX]
        self._attr_unique_id = f"{prefix}_tray_{tray}_color"
        self._attr_name = f"Tray {tray} Color"

    @property
    def native_value(self) -> str | None:
        spool = self._store.get_spool_for_tray(self._tray)
        return spool.color_hex if spool else None

    @property
    def extra_state_attributes(self) -> dict:
        spool = self._store.get_spool_for_tray(self._tray)
        return {
            "spool_id": spool.spool_id if spool else None,
            "material": spool.material_type if spool else None,
        }


class TrayMaterialSensor(_BaseFilamentSensor):
    _attr_icon = "mdi:printer-3d"

    def __init__(self, store: SpoolStore, entry: ConfigEntry, tray: int) -> None:
        super().__init__(store, entry)
        self._tray = tray
        prefix = entry.data[CONF_ENTITY_PREFIX]
        self._attr_unique_id = f"{prefix}_tray_{tray}_material"
        self._attr_name = f"Tray {tray} Material"

    @property
    def native_value(self) -> str | None:
        spool = self._store.get_spool_for_tray(self._tray)
        return spool.material_type if spool else None

    @property
    def extra_state_attributes(self) -> dict:
        spool = self._store.get_spool_for_tray(self._tray)
        return {
            "spool_id": spool.spool_id if spool else None,
            "brand": spool.brand if spool else None,
        }


class TotalConsumedSensor(_BaseFilamentSensor):
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


class LastPrintUsageSensor(_BaseFilamentSensor):
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
