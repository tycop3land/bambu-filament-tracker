"""Bambu Filament Tracker integration for Home Assistant."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import (
    CONF_DEFAULT_SPOOL_WEIGHT_G,
    DEFAULT_SPOOL_WEIGHT_G,
    DOMAIN,
    SIGNAL_FILAMENT_UPDATE,
)
from .spool_registry import SpoolRegistry
from .store import SpoolStore
from .tracker import ConsumptionTracker

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

PLATFORMS = ["sensor", "binary_sensor"]

CARD_PATH = Path(__file__).parent / "bambu-filament-tracker-card.js"


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the Bambu Filament Tracker component."""
    www_dir = Path(hass.config.path("www"))
    www_dir.mkdir(exist_ok=True)
    dest = www_dir / "bambu-filament-tracker-card.js"
    if CARD_PATH.exists():
        shutil.copy2(str(CARD_PATH), str(dest))
        _LOGGER.info("Filament tracker card copied to %s", dest)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Bambu Filament Tracker from a config entry."""
    store = SpoolStore(hass, entry.entry_id)
    await store.async_load()

    registry = SpoolRegistry(hass, store)
    tracker = ConsumptionTracker(hass, entry, store, registry)

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "store": store,
        "registry": registry,
        "tracker": tracker,
    }

    _register_services(hass, entry)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await tracker.async_start()

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    data = hass.data[DOMAIN].get(entry.entry_id)
    if data:
        tracker: ConsumptionTracker = data["tracker"]
        await tracker.async_stop()

    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id, None)
        if not hass.data[DOMAIN]:
            hass.data.pop(DOMAIN)
            for service in (
                "register_spool", "load_spool", "unload_spool",
                "adjust_remaining", "sync_from_tray",
            ):
                hass.services.async_remove(DOMAIN, service)

    return unloaded


def _get_registry(hass: HomeAssistant) -> tuple[SpoolRegistry, SpoolStore]:
    """Get the first available registry and store."""
    for data in hass.data.get(DOMAIN, {}).values():
        return data["registry"], data["store"]
    raise HomeAssistantError("Filament Tracker not configured")


def _register_services(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Register integration services (idempotent)."""
    if hass.services.has_service(DOMAIN, "register_spool"):
        return

    async def handle_register_spool(call: ServiceCall) -> None:
        registry, store = _get_registry(hass)
        default_weight = entry.data.get(CONF_DEFAULT_SPOOL_WEIGHT_G, DEFAULT_SPOOL_WEIGHT_G)
        registry.register_spool(
            color_hex=call.data["color_hex"],
            material_type=call.data["material_type"],
            name=call.data["name"],
            brand=call.data.get("brand", ""),
            initial_weight_g=call.data.get("initial_weight_g", default_weight),
            remaining_weight_g=call.data.get("remaining_weight_g"),
        )
        await store.async_save()
        async_dispatcher_send(hass, SIGNAL_FILAMENT_UPDATE)

    async def handle_load_spool(call: ServiceCall) -> None:
        registry, store = _get_registry(hass)
        success = registry.load_spool(
            spool_id=call.data["spool_id"],
            tray_index=call.data["tray_index"],
        )
        if not success:
            raise HomeAssistantError(f"Spool {call.data['spool_id']} not found")
        await store.async_save()
        async_dispatcher_send(hass, SIGNAL_FILAMENT_UPDATE)

    async def handle_unload_spool(call: ServiceCall) -> None:
        registry, store = _get_registry(hass)
        registry.unload_spool(tray_index=call.data["tray_index"])
        await store.async_save()
        async_dispatcher_send(hass, SIGNAL_FILAMENT_UPDATE)

    async def handle_adjust_remaining(call: ServiceCall) -> None:
        registry, store = _get_registry(hass)
        success = registry.adjust_remaining(
            spool_id=call.data["spool_id"],
            remaining_weight_g=call.data["remaining_weight_g"],
        )
        if not success:
            raise HomeAssistantError(f"Spool {call.data['spool_id']} not found")
        await store.async_save()
        async_dispatcher_send(hass, SIGNAL_FILAMENT_UPDATE)

    async def handle_sync_from_tray(call: ServiceCall) -> None:
        registry, store = _get_registry(hass)
        for data in hass.data.get(DOMAIN, {}).values():
            tracker: ConsumptionTracker = data["tracker"]
            tray_index = call.data.get("tray_index")
            trays = [tray_index] if tray_index else range(1, 5)
            prefix = entry.data["entity_prefix"]
            for idx in trays:
                entity_id = f"sensor.{prefix}_tray_{idx}"
                state = hass.states.get(entity_id)
                if state and state.state not in ("unavailable", "unknown"):
                    await tracker._process_tray_change(entity_id, state)
            break
        await store.async_save()
        async_dispatcher_send(hass, SIGNAL_FILAMENT_UPDATE)

    hass.services.async_register(
        DOMAIN, "register_spool", handle_register_spool,
        schema=vol.Schema({
            vol.Required("color_hex"): cv.string,
            vol.Required("material_type"): cv.string,
            vol.Required("name"): cv.string,
            vol.Optional("brand"): cv.string,
            vol.Optional("initial_weight_g"): vol.Coerce(float),
            vol.Optional("remaining_weight_g"): vol.Coerce(float),
        }),
    )

    hass.services.async_register(
        DOMAIN, "load_spool", handle_load_spool,
        schema=vol.Schema({
            vol.Required("spool_id"): cv.string,
            vol.Required("tray_index"): vol.All(int, vol.Range(min=1, max=4)),
        }),
    )

    hass.services.async_register(
        DOMAIN, "unload_spool", handle_unload_spool,
        schema=vol.Schema({
            vol.Required("tray_index"): vol.All(int, vol.Range(min=1, max=4)),
        }),
    )

    hass.services.async_register(
        DOMAIN, "adjust_remaining", handle_adjust_remaining,
        schema=vol.Schema({
            vol.Required("spool_id"): cv.string,
            vol.Required("remaining_weight_g"): vol.Coerce(float),
        }),
    )

    hass.services.async_register(
        DOMAIN, "sync_from_tray", handle_sync_from_tray,
        schema=vol.Schema({
            vol.Optional("tray_index"): vol.All(int, vol.Range(min=1, max=4)),
        }),
    )
