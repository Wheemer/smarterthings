"""SmarterThings."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
import logging
from typing import Any

from pysmartthings import Capability, Command, SmartThingsError
import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_DEVICE_ID, Platform
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_call_later, async_track_time_change
from homeassistant.util import dt as dt_util

from .const import (
    CONF_NIGHTLY_SYNC_TIME,
    CONF_STARTUP_SYNC_DELAY,
    CONF_STARTUP_SYNC_ENABLED,
    DEFAULT_NIGHTLY_SYNC_TIME,
    DEFAULT_STARTUP_SYNC_DELAY,
    DEFAULT_STARTUP_SYNC_ENABLED,
    DOMAIN,
    SERVICE_SYNC_TIME,
    SIGNAL_SYNCED,
)

_LOGGER = logging.getLogger(__name__)


@dataclass
class RangeClockRuntime:
    """Runtime data for one configured range clock."""

    entry: ConfigEntry
    smartthings_device_id: str
    unsubscribers: list
    last_sync_at: str | None = None
    last_sync_reason: str | None = None
    last_error: str | None = None


type RangeClockConfigEntry = ConfigEntry[RangeClockRuntime]

PLATFORMS = [Platform.BUTTON, Platform.SENSOR]


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Set up services."""

    async def handle_sync_time(call: ServiceCall) -> None:
        entries = list(hass.config_entries.async_entries(DOMAIN))

        if not entries:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="no_configured_range",
                translation_placeholders={},
            )

        for entry in entries:
            runtime = entry.runtime_data
            await _sync_range_clock(hass, runtime, "manual")

    hass.services.async_register(
        DOMAIN,
        SERVICE_SYNC_TIME,
        handle_sync_time,
        schema=vol.Schema({}),
    )
    return True


async def async_setup_entry(
    hass: HomeAssistant, entry: RangeClockConfigEntry
) -> bool:
    """Set up a configured range clock."""
    runtime = RangeClockRuntime(
        entry=entry,
        smartthings_device_id=entry.data[CONF_DEVICE_ID],
        unsubscribers=[],
    )
    entry.runtime_data = runtime

    _schedule_startup_sync(hass, runtime)
    _schedule_nightly_sync(hass, runtime)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: RangeClockConfigEntry
) -> bool:
    """Unload a configured range clock."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if not unload_ok:
        return False
    for unsubscribe in entry.runtime_data.unsubscribers:
        unsubscribe()
    return True


async def _async_update_listener(
    hass: HomeAssistant, entry: RangeClockConfigEntry
) -> None:
    """Reload when options change."""
    await hass.config_entries.async_reload(entry.entry_id)


def _get_options(entry: ConfigEntry) -> dict[str, Any]:
    """Return options with defaults."""
    return {
        CONF_STARTUP_SYNC_ENABLED: entry.options.get(
            CONF_STARTUP_SYNC_ENABLED, DEFAULT_STARTUP_SYNC_ENABLED
        ),
        CONF_STARTUP_SYNC_DELAY: entry.options.get(
            CONF_STARTUP_SYNC_DELAY, DEFAULT_STARTUP_SYNC_DELAY
        ),
        CONF_NIGHTLY_SYNC_TIME: entry.options.get(
            CONF_NIGHTLY_SYNC_TIME, DEFAULT_NIGHTLY_SYNC_TIME
        ),
    }


def _schedule_startup_sync(
    hass: HomeAssistant, runtime: RangeClockRuntime
) -> None:
    """Schedule startup sync if enabled."""
    options = _get_options(runtime.entry)
    if not options[CONF_STARTUP_SYNC_ENABLED]:
        return

    delay = timedelta(minutes=float(options[CONF_STARTUP_SYNC_DELAY]))

    async def _startup_sync(now) -> None:
        await _sync_range_clock(hass, runtime, "startup")

    runtime.unsubscribers.append(async_call_later(hass, delay, _startup_sync))


def _schedule_nightly_sync(
    hass: HomeAssistant, runtime: RangeClockRuntime
) -> None:
    """Schedule daily sync at configured local time."""
    hour, minute, second = _parse_time(_get_options(runtime.entry)[CONF_NIGHTLY_SYNC_TIME])

    async def _nightly_sync(now) -> None:
        await _sync_range_clock(hass, runtime, "scheduled")

    runtime.unsubscribers.append(
        async_track_time_change(
            hass,
            _nightly_sync,
            hour=hour,
            minute=minute,
            second=second,
        )
    )


def _parse_time(value: str) -> tuple[int, int, int]:
    """Parse HH:MM or HH:MM:SS."""
    parts = [int(part) for part in value.split(":")]
    if len(parts) == 2:
        parts.append(0)
    return parts[0], parts[1], parts[2]


async def _sync_range_clock(
    hass: HomeAssistant, runtime: RangeClockRuntime, reason: str
) -> None:
    """Send the Samsung current time execute command."""
    smartthings_client = _get_smartthings_client(hass, runtime.smartthings_device_id)
    current_time = dt_util.now().strftime("%Y-%m-%dT%H:%M:%S")
    arguments = [
        "/configuration/vs/0",
        {"x.com.samsung.da.currentTime": current_time},
    ]

    try:
        await smartthings_client.execute_device_command(
            runtime.smartthings_device_id,
            Capability.EXECUTE,
            Command.EXECUTE,
            argument=arguments,
        )
    except SmartThingsError as err:
        runtime.last_error = str(err)
        _LOGGER.exception("Failed to sync Samsung range clock")
        raise HomeAssistantError(f"Failed to sync Samsung range clock: {err}") from err

    runtime.last_sync_at = dt_util.utcnow().isoformat()
    runtime.last_sync_reason = reason
    runtime.last_error = None
    async_dispatcher_send(hass, SIGNAL_SYNCED, runtime.entry.entry_id)
    _LOGGER.info(
        "Synced Samsung range clock for %s (%s)",
        runtime.smartthings_device_id,
        reason,
    )


def _get_smartthings_client(hass: HomeAssistant, smartthings_device_id: str):
    """Return the official SmartThings client for the matching device."""
    for entry in hass.config_entries.async_entries("smartthings"):
        data = entry.runtime_data
        if smartthings_device_id in data.devices:
            return data.client
    raise HomeAssistantError(
        f"SmartThings device {smartthings_device_id} is not loaded"
    )
