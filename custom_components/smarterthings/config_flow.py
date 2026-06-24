"""Config flow for SmarterThings."""

from __future__ import annotations

from datetime import time
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_DEVICE_ID
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers import selector

from .const import (
    CONF_NIGHTLY_SYNC_TIME,
    CONF_RANGE_ENTITY_ID,
    CONF_STARTUP_SYNC_DELAY,
    CONF_STARTUP_SYNC_ENABLED,
    DEFAULT_NIGHTLY_SYNC_TIME,
    DEFAULT_STARTUP_SYNC_DELAY,
    DEFAULT_STARTUP_SYNC_ENABLED,
    DOMAIN,
)


def _schema(defaults: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(
                CONF_RANGE_ENTITY_ID,
                default=defaults.get(CONF_RANGE_ENTITY_ID),
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(integration="smartthings")
            ),
            vol.Required(
                CONF_STARTUP_SYNC_ENABLED,
                default=defaults.get(
                    CONF_STARTUP_SYNC_ENABLED, DEFAULT_STARTUP_SYNC_ENABLED
                ),
            ): bool,
            vol.Required(
                CONF_STARTUP_SYNC_DELAY,
                default=defaults.get(
                    CONF_STARTUP_SYNC_DELAY, DEFAULT_STARTUP_SYNC_DELAY
                ),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0,
                    max=120,
                    step=1,
                    mode=selector.NumberSelectorMode.BOX,
                    unit_of_measurement="min",
                )
            ),
            vol.Required(
                CONF_NIGHTLY_SYNC_TIME,
                default=defaults.get(CONF_NIGHTLY_SYNC_TIME, DEFAULT_NIGHTLY_SYNC_TIME),
            ): selector.TimeSelector(),
        }
    )


def _normalize_options(user_input: dict[str, Any]) -> dict[str, Any]:
    """Normalize selector output before saving options."""
    normalized = dict(user_input)
    sync_time = normalized[CONF_NIGHTLY_SYNC_TIME]
    if isinstance(sync_time, time):
        normalized[CONF_NIGHTLY_SYNC_TIME] = sync_time.isoformat()
    return normalized


def _resolve_smartthings_device_id(
    hass: HomeAssistant, entity_id: str
) -> tuple[str | None, str | None]:
    entity_entry = er.async_get(hass).async_get(entity_id)
    if entity_entry is None or entity_entry.platform != "smartthings":
        return None, "not_smartthings"
    if entity_entry.device_id is None:
        return None, "no_device"

    device_entry = dr.async_get(hass).async_get(entity_entry.device_id)
    if device_entry is None:
        return None, "no_device"

    for domain, identifier in device_entry.identifiers:
        if domain == "smartthings":
            return identifier, None
    return None, "no_smartthings_identifier"


class SmartThingsRangeClockConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for SmarterThings."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            user_input = _normalize_options(user_input)
            smartthings_device_id, error = _resolve_smartthings_device_id(
                self.hass, user_input[CONF_RANGE_ENTITY_ID]
            )
            if error is not None:
                errors["base"] = error
            else:
                await self.async_set_unique_id(smartthings_device_id)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title="SmarterThings",
                    data={
                        CONF_DEVICE_ID: smartthings_device_id,
                        CONF_RANGE_ENTITY_ID: user_input[CONF_RANGE_ENTITY_ID],
                    },
                    options={
                        CONF_RANGE_ENTITY_ID: user_input[CONF_RANGE_ENTITY_ID],
                        CONF_STARTUP_SYNC_ENABLED: user_input[
                            CONF_STARTUP_SYNC_ENABLED
                        ],
                        CONF_STARTUP_SYNC_DELAY: user_input[CONF_STARTUP_SYNC_DELAY],
                        CONF_NIGHTLY_SYNC_TIME: user_input[CONF_NIGHTLY_SYNC_TIME],
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=_schema({}),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> SmartThingsRangeClockOptionsFlow:
        """Create the options flow."""
        return SmartThingsRangeClockOptionsFlow()


class SmartThingsRangeClockOptionsFlow(config_entries.OptionsFlow):
    """Handle options for SmarterThings."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Manage options."""
        errors: dict[str, str] = {}

        if user_input is not None:
            user_input = _normalize_options(user_input)
            smartthings_device_id, error = _resolve_smartthings_device_id(
                self.hass, user_input[CONF_RANGE_ENTITY_ID]
            )
            if error is not None:
                errors["base"] = error
            elif smartthings_device_id != self.config_entry.data[CONF_DEVICE_ID]:
                errors["base"] = "no_smartthings_identifier"
            else:
                return self.async_create_entry(title="", data=user_input)

        defaults = {
            **self.config_entry.data,
            **self.config_entry.options,
        }
        return self.async_show_form(
            step_id="init",
            data_schema=_schema(defaults),
            errors=errors,
        )
