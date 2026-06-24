"""Sensor entities for Even SmarterThings."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, UnitOfEnergy, UnitOfPower
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from . import RangeClockRuntime, _get_smartthings_client
from .const import SIGNAL_SYNCED

SCAN_INTERVAL = timedelta(minutes=10)

EXTRA_CAPABILITY_PREFIXES = ("custom.", "samsungce.", "sec.")
EXTRA_STANDARD_CAPABILITIES = {"remoteControlStatus"}
POWER_CONSUMPTION_CAPABILITY = "powerConsumptionReport"
POWER_CONSUMPTION_ATTRIBUTE = "powerConsumption"


@dataclass(frozen=True)
class StatusPath:
    """One flattened SmartThings status path."""

    component: str
    capability: str
    attribute: str

    @property
    def key(self) -> str:
        """Return a stable key."""
        return f"{self.component}_{self.capability}_{self.attribute}".replace(".", "_")

    @property
    def name(self) -> str:
        """Return a human readable name."""
        bits = [self.component, self.capability, self.attribute]
        return " ".join(bit.replace(".", " ").replace("_", " ") for bit in bits)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry[RangeClockRuntime],
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensors."""
    runtime = entry.runtime_data
    entities: list[SensorEntity] = [
        LastSyncSensor(entry),
        LastSyncStatusSensor(entry),
    ]

    for smartthings_entry in hass.config_entries.async_entries("smartthings"):
        data = smartthings_entry.runtime_data
        for device_id, full_device in data.devices.items():
            paths = _extra_status_paths(full_device.status)
            if _has_power_consumption(full_device.status):
                entities.extend(
                    [
                        AppliancePowerSensor(
                            hass=hass,
                            smartthings_device_id=device_id,
                            device_name=device_name,
                        ),
                        ApplianceEnergySensor(
                            hass=hass,
                            smartthings_device_id=device_id,
                            device_name=device_name,
                        ),
                    ]
                )
            if not paths:
                continue
            device_name = full_device.device.label or full_device.device.name
            for path in paths:
                entities.append(
                    SmartThingsExtraStatusSensor(
                        hass=hass,
                        smartthings_device_id=device_id,
                        device_name=device_name,
                        path=path,
                    )
                )

    async_add_entities(entities)


class LastSyncSensor(SensorEntity):
    """Last successful range clock sync time."""

    _attr_has_entity_name = True
    _attr_name = "Last clock sync"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, entry: ConfigEntry[RangeClockRuntime]) -> None:
        """Initialize the sensor."""
        self.entry = entry
        self.runtime = entry.runtime_data
        self._attr_unique_id = f"{self.runtime.smartthings_device_id}_last_clock_sync"
        self._attr_device_info = DeviceInfo(
            identifiers={("smartthings", self.runtime.smartthings_device_id)}
        )

    @property
    def native_value(self):
        """Return last sync time."""
        if self.runtime.last_sync_at is None:
            return None
        return dt_util.parse_datetime(self.runtime.last_sync_at)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return sync metadata."""
        return {
            "reason": self.runtime.last_sync_reason,
            "last_error": self.runtime.last_error,
        }

    async def async_added_to_hass(self) -> None:
        """Subscribe to sync updates."""
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_SYNCED,
                self._handle_sync_update,
            )
        )

    @callback
    def _handle_sync_update(self, entry_id: str) -> None:
        """Handle a sync update."""
        if entry_id == self.entry.entry_id:
            self.async_write_ha_state()


class LastSyncStatusSensor(SensorEntity):
    """Last range clock sync status."""

    _attr_has_entity_name = True
    _attr_name = "Clock sync status"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, entry: ConfigEntry[RangeClockRuntime]) -> None:
        """Initialize the sensor."""
        self.entry = entry
        self.runtime = entry.runtime_data
        self._attr_unique_id = f"{self.runtime.smartthings_device_id}_clock_sync_status"
        self._attr_device_info = DeviceInfo(
            identifiers={("smartthings", self.runtime.smartthings_device_id)}
        )

    @property
    def native_value(self) -> str:
        """Return current sync status."""
        return "error" if self.runtime.last_error else "ok"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return sync metadata."""
        return {
            "last_sync_at": self.runtime.last_sync_at,
            "reason": self.runtime.last_sync_reason,
            "last_error": self.runtime.last_error,
        }

    async def async_added_to_hass(self) -> None:
        """Subscribe to sync updates."""
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_SYNCED,
                self._handle_sync_update,
            )
        )

    @callback
    def _handle_sync_update(self, entry_id: str) -> None:
        """Handle a sync update."""
        if entry_id == self.entry.entry_id:
            self.async_write_ha_state()


class SmartThingsExtraStatusSensor(SensorEntity):
    """Generic read-only Samsung appliance extra status sensor."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        hass: HomeAssistant,
        smartthings_device_id: str,
        device_name: str,
        path: StatusPath,
    ) -> None:
        """Initialize the sensor."""
        self.hass = hass
        self.smartthings_device_id = smartthings_device_id
        self.path = path
        self._attr_name = path.name
        self._attr_unique_id = f"{smartthings_device_id}_{path.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={("smartthings", smartthings_device_id)},
            name=device_name,
        )
        self._attr_native_value = None
        self._attr_extra_state_attributes = {}

    async def async_update(self) -> None:
        """Fetch current SmartThings status."""
        client = _get_smartthings_client(self.hass, self.smartthings_device_id)
        status = await client.get_device_status(self.smartthings_device_id)
        value, attrs = _read_status_path(status, self.path)
        self._attr_native_value = value
        self._attr_extra_state_attributes = attrs


class AppliancePowerSensor(SensorEntity):
    """Replacement Samsung appliance power sensor."""

    _attr_has_entity_name = True
    _attr_name = "Samsung power"
    _attr_device_class = SensorDeviceClass.POWER
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        hass: HomeAssistant,
        smartthings_device_id: str,
        device_name: str,
    ) -> None:
        """Initialize the sensor."""
        self.hass = hass
        self.smartthings_device_id = smartthings_device_id
        self._attr_unique_id = f"{smartthings_device_id}_samsung_power"
        self._attr_device_info = DeviceInfo(
            identifiers={("smartthings", smartthings_device_id)},
            name=device_name,
        )
        self._attr_native_value = None
        self._attr_extra_state_attributes = {}

    async def async_update(self) -> None:
        """Fetch current SmartThings power consumption status."""
        client = _get_smartthings_client(self.hass, self.smartthings_device_id)
        status = await client.get_device_status(self.smartthings_device_id)
        report, attrs = _power_consumption_report(status)
        self._attr_native_value = report.get("power") if report else None
        self._attr_extra_state_attributes = attrs


class ApplianceEnergySensor(SensorEntity):
    """Replacement Samsung appliance energy sensor."""

    _attr_has_entity_name = True
    _attr_name = "Samsung energy"
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_state_class = SensorStateClass.TOTAL_INCREASING

    def __init__(
        self,
        hass: HomeAssistant,
        smartthings_device_id: str,
        device_name: str,
    ) -> None:
        """Initialize the sensor."""
        self.hass = hass
        self.smartthings_device_id = smartthings_device_id
        self._attr_unique_id = f"{smartthings_device_id}_samsung_energy"
        self._attr_device_info = DeviceInfo(
            identifiers={("smartthings", smartthings_device_id)},
            name=device_name,
        )
        self._attr_native_value = None
        self._attr_extra_state_attributes = {}

    async def async_update(self) -> None:
        """Fetch current SmartThings power consumption status."""
        client = _get_smartthings_client(self.hass, self.smartthings_device_id)
        status = await client.get_device_status(self.smartthings_device_id)
        report, attrs = _power_consumption_report(status)
        energy_wh = report.get("energy") if report else None
        self._attr_native_value = (
            round(float(energy_wh) / 1000, 3) if energy_wh is not None else None
        )
        self._attr_extra_state_attributes = attrs


def _extra_status_paths(status: dict[str, Any]) -> list[StatusPath]:
    """Return safe scalar Samsung-specific status paths."""
    paths: list[StatusPath] = []
    for component, capabilities in status.items():
        for capability, attributes in capabilities.items():
            capability_name = str(capability)
            if not (
                capability_name.startswith(EXTRA_CAPABILITY_PREFIXES)
                or capability_name in EXTRA_STANDARD_CAPABILITIES
            ):
                continue
            for attribute, state in attributes.items():
                value = _state_value(state)
                if value is None or isinstance(value, (dict, list)):
                    continue
                paths.append(StatusPath(component, capability_name, str(attribute)))
    return paths


def _has_power_consumption(status: dict[str, Any]) -> bool:
    """Return true if the device exposes Samsung power consumption."""
    return bool(_power_consumption_report(status)[0])


def _power_consumption_report(status: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return Samsung power consumption report and attributes."""
    state = (
        status.get("main", {})
        .get(POWER_CONSUMPTION_CAPABILITY, {})
        .get(POWER_CONSUMPTION_ATTRIBUTE)
    )
    value = _state_value(state)
    if not isinstance(value, dict):
        return {}, {}

    attrs = {
        key: val
        for key, val in value.items()
        if key
        not in {
            "power",
            "energy",
        }
    }
    timestamp = getattr(state, "timestamp", None)
    if timestamp is not None:
        attrs["smartthings_timestamp"] = str(timestamp)
    return value, attrs


def _read_status_path(
    status: dict[str, Any], path: StatusPath
) -> tuple[Any, dict[str, Any]]:
    """Read a status path."""
    state = (
        status.get(path.component, {})
        .get(path.capability, {})
        .get(path.attribute)
    )
    value = _state_value(state)
    attrs: dict[str, Any] = {}
    if state is not None:
        unit = getattr(state, "unit", None)
        timestamp = getattr(state, "timestamp", None)
        if unit is not None:
            attrs["unit"] = unit
        if timestamp is not None:
            attrs["smartthings_timestamp"] = str(timestamp)
    return value, attrs


def _state_value(state: Any) -> Any:
    """Return a primitive state value."""
    if state is None:
        return None
    return getattr(state, "value", state.get("value") if isinstance(state, dict) else None)
