"""Button entities for SmarterThings."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_DEVICE_ID
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import RangeClockRuntime, _get_smartthings_client, _sync_range_clock


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry[RangeClockRuntime],
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up range clock buttons."""
    async_add_entities([RangeClockSyncButton(hass, entry)])
    await _disable_phantom_second_cavity_entities(hass, entry.runtime_data)


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


async def _disable_phantom_second_cavity_entities(
    hass: HomeAssistant, runtime: RangeClockRuntime
) -> None:
    """Disable official SmartThings second-cavity entities for single-cavity ranges."""
    client = _get_smartthings_client(hass, runtime.smartthings_device_id)
    status = await client.get_device_status(runtime.smartthings_device_id)
    if not _is_phantom_second_cavity(status):
        return

    device_entry = dr.async_get(hass).async_get_device(
        identifiers={("smartthings", runtime.smartthings_device_id)}
    )
    if device_entry is None:
        return

    registry = er.async_get(hass)
    for entity_entry in list(registry.entities.values()):
        if (
            entity_entry.platform == "smartthings"
            and entity_entry.device_id == device_entry.id
            and "second_cavity" in entity_entry.entity_id
            and entity_entry.disabled_by is None
        ):
            registry.async_update_entity(
                entity_entry.entity_id,
                disabled_by=er.RegistryEntryDisabler.INTEGRATION,
            )


def _is_phantom_second_cavity(status: dict) -> bool:
    """Return true if cavity-01 has no meaningful second-cavity state."""
    cavity = status.get("cavity-01")
    if not isinstance(cavity, dict):
        return False

    meaningful_paths = (
        ("ovenMode", "ovenMode"),
        ("ovenOperatingState", "machineState"),
        ("ovenOperatingState", "ovenJobState"),
        ("ovenOperatingState", "completionTime"),
        ("ovenOperatingState", "operationTime"),
        ("ovenOperatingState", "progress"),
        ("ovenSetpoint", "ovenSetpoint"),
        ("samsungce.ovenMode", "ovenMode"),
        ("samsungce.ovenOperatingState", "operatingState"),
        ("samsungce.ovenOperatingState", "ovenJobState"),
        ("samsungce.ovenOperatingState", "completionTime"),
        ("samsungce.ovenOperatingState", "operationTime"),
        ("samsungce.ovenOperatingState", "progress"),
        ("temperatureMeasurement", "temperature"),
    )
    return all(
        _status_value(cavity, capability, attribute) is None
        for capability, attribute in meaningful_paths
    )


def _status_value(component: dict, capability: str, attribute: str):
    """Return a nested SmartThings status value."""
    state = component.get(capability, {}).get(attribute)
    if state is None:
        return None
    return getattr(state, "value", state.get("value") if isinstance(state, dict) else None)
