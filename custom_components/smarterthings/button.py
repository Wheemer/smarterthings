"""Button entities for SmarterThings."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_DEVICE_ID
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from . import RangeClockRuntime, _sync_range_clock


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry[RangeClockRuntime],
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up range clock buttons."""
    async_add_entities([RangeClockSyncButton(hass, entry)])


class RangeClockSyncButton(ButtonEntity):
    """Button that syncs the configured range clock."""

    _attr_has_entity_name = True
    _attr_name = "Sync clock"

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry[RangeClockRuntime]
    ) -> None:
        """Initialize the button."""
        self.hass = hass
        self.entry = entry
        self.runtime = entry.runtime_data
        self._attr_unique_id = f"{self.runtime.smartthings_device_id}_sync_clock"
        self._attr_device_info = DeviceInfo(
            identifiers={("smartthings", self.runtime.smartthings_device_id)}
        )

    async def async_press(self) -> None:
        """Sync the range clock."""
        await _sync_range_clock(self.hass, self.runtime, "button")
