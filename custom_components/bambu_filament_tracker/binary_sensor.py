"""Binary sensor platform for Bambu Filament Tracker."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_DEVICE_NAME,
    CONF_ENTITY_PREFIX,
    CONF_LOW_THRESHOLD_PCT,
    DEFAULT_LOW_THRESHOLD_PCT,
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

    entities = [TrayLowBinarySensor(store, entry, tray) for tray in range(1, NUM_TRAYS + 1)]
    async_add_entities(entities)


class TrayLowBinarySensor(BinarySensorEntity):
    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_icon = "mdi:alert-circle-outline"

    def __init__(self, store: SpoolStore, entry: ConfigEntry, tray: int) -> None:
        self._store = store
        self._entry = entry
        self._tray = tray
        prefix = entry.data[CONF_ENTITY_PREFIX]
        self._attr_unique_id = f"{prefix}_tray_{tray}_low"
        self._attr_name = f"Tray {tray} Low"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, prefix)},
            name=f"Filament Tracker ({entry.data[CONF_DEVICE_NAME]})",
            manufacturer="Bambu Lab",
            model="AMS Filament Tracker",
        )

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
    def is_on(self) -> bool | None:
        spool = self._store.get_spool_for_tray(self._tray)
        if spool is None or spool.initial_weight_g <= 0:
            return None
        threshold = self._entry.data.get(CONF_LOW_THRESHOLD_PCT, DEFAULT_LOW_THRESHOLD_PCT)
        remaining_pct = spool.remaining_weight_g / spool.initial_weight_g * 100
        return remaining_pct < threshold
