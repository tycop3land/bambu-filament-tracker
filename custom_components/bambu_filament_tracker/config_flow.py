"""Config flow for Bambu Filament Tracker."""

from __future__ import annotations

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow

from .const import (
    CONF_DEFAULT_SPOOL_WEIGHT_G,
    CONF_DEVICE_NAME,
    CONF_ENTITY_PREFIX,
    CONF_LOW_THRESHOLD_PCT,
    CONF_TARGET_AMS,
    DEFAULT_LOW_THRESHOLD_PCT,
    DEFAULT_SPOOL_WEIGHT_G,
    DEFAULT_TARGET_AMS,
    DOMAIN,
)


class BambuFilamentTrackerConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Bambu Filament Tracker."""

    VERSION = 1

    def __init__(self) -> None:
        self._prefix: str | None = None
        self._name: str | None = None

    async def async_step_user(self, user_input=None):
        """Step 1: Select Bambu Lab printer."""
        bambu_printers = {}
        for state in self.hass.states.async_all("sensor"):
            if state.entity_id.endswith("_print_status"):
                options = state.attributes.get("options", [])
                if isinstance(options, list) and "running" in options:
                    prefix = state.entity_id.replace("sensor.", "").replace("_print_status", "")
                    friendly = state.attributes.get("friendly_name", prefix)
                    name = friendly.replace(" Print Status", "").replace(" Print status", "")
                    bambu_printers[prefix] = name

        if not bambu_printers:
            return self.async_abort(reason="no_bambu_printers")

        if user_input is not None:
            self._prefix = user_input["printer"]
            self._name = bambu_printers[self._prefix]
            await self.async_set_unique_id(self._prefix)
            self._abort_if_unique_id_configured()
            return await self.async_step_options()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {vol.Required("printer"): vol.In(bambu_printers)}
            ),
        )

    async def async_step_options(self, user_input=None):
        """Step 2: Configure thresholds."""
        if user_input is not None:
            return self.async_create_entry(
                title=f"Filament Tracker ({self._name})",
                data={
                    CONF_ENTITY_PREFIX: self._prefix,
                    CONF_DEVICE_NAME: self._name,
                    CONF_LOW_THRESHOLD_PCT: user_input.get(
                        CONF_LOW_THRESHOLD_PCT, DEFAULT_LOW_THRESHOLD_PCT
                    ),
                    CONF_DEFAULT_SPOOL_WEIGHT_G: user_input.get(
                        CONF_DEFAULT_SPOOL_WEIGHT_G, DEFAULT_SPOOL_WEIGHT_G
                    ),
                    CONF_TARGET_AMS: user_input.get(
                        CONF_TARGET_AMS, DEFAULT_TARGET_AMS
                    ),
                },
            )

        return self.async_show_form(
            step_id="options",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_LOW_THRESHOLD_PCT,
                        default=DEFAULT_LOW_THRESHOLD_PCT,
                    ): vol.All(int, vol.Range(min=1, max=50)),
                    vol.Optional(
                        CONF_DEFAULT_SPOOL_WEIGHT_G,
                        default=DEFAULT_SPOOL_WEIGHT_G,
                    ): vol.All(int, vol.Range(min=100, max=5000)),
                    vol.Optional(
                        CONF_TARGET_AMS,
                        default=DEFAULT_TARGET_AMS,
                    ): vol.All(int, vol.Range(min=1, max=4)),
                }
            ),
        )
