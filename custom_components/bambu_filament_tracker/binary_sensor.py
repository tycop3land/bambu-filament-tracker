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
    CONF_LOW_THRESHOLD_PCT,
    DEFAULT_LOW_THRESHOLD_PCT,
    DOMAIN,
    SIGNAL_FILAMENT_UPDATE,
    SIGNAL_NEW_SPOOL,
)
from .models import Spool
from .sensor import _filament_device_info
from .store import SpoolStore


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    store: SpoolStore = data["store"]

    entities = [
        SpoolLowBinarySensor(store, entry, spool.spool_id)
        for spool in store.spools.values()
    ]
    async_add_entities(entities)

    @callback
    def _on_new_spool(spool_id: str) -> None:
        spool = store.get_spool(spool_id)
        if spool is None:
            return
        async_add_entities([SpoolLowBinarySensor(store, entry, spool_id)])

    entry.async_on_unload(
        async_dispatcher_connect(hass, SIGNAL_NEW_SPOOL, _on_new_spool)
    )


class SpoolLowBinarySensor(BinarySensorEntity):
    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_icon = "mdi:alert-circle-outline"

    def __init__(self, store: SpoolStore, entry: ConfigEntry, spool_id: str) -> None:
        self._store = store
        self._entry = entry
        self._spool_id = spool_id
        self._attr_unique_id = f"spool_{spool_id}_low"
        self._attr_name = "Low Filament"

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
    def is_on(self) -> bool | None:
        spool = self._spool()
        if spool is None or spool.initial_weight_g <= 0:
            return None
        threshold = self._entry.data.get(CONF_LOW_THRESHOLD_PCT, DEFAULT_LOW_THRESHOLD_PCT)
        remaining_pct = spool.remaining_weight_g / spool.initial_weight_g * 100
        return remaining_pct < threshold
