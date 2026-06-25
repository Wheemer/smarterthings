"""Sensor entities for SmarterThings."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import timedelta
from time import monotonic
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
STATUS_CACHE_TTL = 5


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


@dataclass(frozen=True)
class PowerConsumptionField:
    """One numeric field in Samsung's power consumption report."""

    attribute: str
    name: str
    unique_suffix: str
    device_class: SensorDeviceClass
    native_unit: str
    state_class: SensorStateClass
    scale: float
    entity_category: EntityCategory | None


@dataclass(frozen=True)
class TimestampField:
    """One timestamp field in Samsung's power consumption report."""

    attribute: str
    name: str
    unique_suffix: str


class SmartThingsStatusCache:
    """Short-lived shared SmartThings status cache for one appliance."""

    def __init__(self, hass: HomeAssistant, smartthings_device_id: str) -> None:
        """Initialize the cache."""
        self.hass = hass
        self.smartthings_device_id = smartthings_device_id
        self._lock = asyncio.Lock()
        self._status: dict[str, Any] | None = None
        self._updated_at = 0.0

    async def async_get_status(self) -> dict[str, Any]:
        """Return current status, sharing same-burst entity updates."""
        now = monotonic()
        if self._status is not None and now - self._updated_at < STATUS_CACHE_TTL:
            return self._status

        async with self._lock:
            now = monotonic()
            if self._status is not None and now - self._updated_at < STATUS_CACHE_TTL:
                return self._status

            client = _get_smartthings_client(self.hass, self.smartthings_device_id)
            self._status = await client.get_device_status(self.smartthings_device_id)
            self._updated_at = monotonic()
            return self._status


POWER_CONSUMPTION_NUMERIC_FIELDS: dict[str, PowerConsumptionField] = {
    "power": PowerConsumptionField(
        attribute="power",
        name="Samsung power",
        unique_suffix="samsung_power",
        device_class=SensorDeviceClass.POWER,
        native_unit=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        scale=1,
        entity_category=None,
    ),
    "energy": PowerConsumptionField(
        attribute="energy",
        name="Samsung energy",
        unique_suffix="samsung_energy",
        device_class=SensorDeviceClass.ENERGY,
        native_unit=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL_INCREASING,
        scale=0.001,
        entity_category=None,
    ),
    "deltaEnergy": PowerConsumptionField(
        attribute="deltaEnergy",
        name="Samsung interval energy",
        unique_suffix="samsung_interval_energy",
        device_class=SensorDeviceClass.ENERGY,
        native_unit=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.MEASUREMENT,
        scale=0.001,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    "powerEnergy": PowerConsumptionField(
        attribute="powerEnergy",
        name="Samsung power energy",
        unique_suffix="samsung_power_energy",
        device_class=SensorDeviceClass.ENERGY,
        native_unit=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.MEASUREMENT,
        scale=0.001,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    "persistedEnergy": PowerConsumptionField(
        attribute="persistedEnergy",
        name="Samsung persisted energy",
        unique_suffix="samsung_persisted_energy",
        device_class=SensorDeviceClass.ENERGY,
        native_unit=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.MEASUREMENT,
        scale=0.001,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    "energySaved": PowerConsumptionField(
        attribute="energySaved",
        name="Samsung energy saved",
        unique_suffix="samsung_energy_saved",
        device_class=SensorDeviceClass.ENERGY,
        native_unit=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.MEASUREMENT,
        scale=0.001,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    "persistedSavedEnergy": PowerConsumptionField(
        attribute="persistedSavedEnergy",
        name="Samsung persisted saved energy",
        unique_suffix="samsung_persisted_saved_energy",
        device_class=SensorDeviceClass.ENERGY,
        native_unit=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.MEASUREMENT,
        scale=0.001,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
}

POWER_CONSUMPTION_TIMESTAMP_FIELDS: dict[str, TimestampField] = {
    "start": TimestampField(
        attribute="start",
        name="Samsung energy report start",
        unique_suffix="samsung_energy_report_start",
    ),
    "end": TimestampField(
        attribute="end",
        name="Samsung energy report end",
        unique_suffix="samsung_energy_report_end",
    ),
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry[RangeClockRuntime],
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensors."""
    entities: list[SensorEntity] = [
        LastSyncSensor(entry),
        LastSyncStatusSensor(entry),
    ]

    for smartthings_entry in hass.config_entries.async_entries("smartthings"):
        data = smartthings_entry.runtime_data
        for device_id, full_device in data.devices.items():
            device_name = full_device.device.label or full_device.device.name
            status_cache = SmartThingsStatusCache(hass, device_id)
            paths = _extra_status_paths(full_device.status)
            report_path, report, _attrs = _power_consumption_report(full_device.status)
            if report:
                entities.extend(
                    _power_consumption_sensors(
                        status_cache=status_cache,
                        smartthings_device_id=device_id,
                        device_name=device_name,
                        report_path=report_path,
                        report=report,
                    )
                )
            if not paths:
                continue
            for path in paths:
                entities.append(
                    SmartThingsExtraStatusSensor(
                        status_cache=status_cache,
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
        status_cache: SmartThingsStatusCache,
        smartthings_device_id: str,
        device_name: str,
        path: StatusPath,
    ) -> None:
        """Initialize the sensor."""
        self.status_cache = status_cache
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
        status = await self.status_cache.async_get_status()
        value, attrs = _read_status_path(status, self.path)
        self._attr_native_value = value
        self._attr_extra_state_attributes = attrs


class PowerConsumptionNumericSensor(SensorEntity):
    """Samsung appliance power consumption numeric sensor."""

    _attr_has_entity_name = True

    def __init__(
        self,
        status_cache: SmartThingsStatusCache,
        smartthings_device_id: str,
        device_name: str,
        report_path: StatusPath,
        field: PowerConsumptionField,
    ) -> None:
        """Initialize the sensor."""
        self.status_cache = status_cache
        self.smartthings_device_id = smartthings_device_id
        self.report_path = report_path
        self.field = field
        self._attr_name = field.name
        self._attr_unique_id = f"{smartthings_device_id}_{field.unique_suffix}"
        self._attr_device_class = field.device_class
        self._attr_native_unit_of_measurement = field.native_unit
        self._attr_state_class = field.state_class
        self._attr_entity_category = field.entity_category
        self._attr_device_info = DeviceInfo(
            identifiers={("smartthings", smartthings_device_id)},
            name=device_name,
        )
        self._attr_native_value = None
        self._attr_extra_state_attributes = {}

    async def async_update(self) -> None:
        """Fetch current SmartThings power consumption status."""
        status = await self.status_cache.async_get_status()
        _report_path, report, attrs = _power_consumption_report(status, self.report_path)
        self._attr_native_value = _scaled_numeric_value(
            report.get(self.field.attribute), self.field.scale
        )
        self._attr_extra_state_attributes = attrs


class PowerConsumptionTimestampSensor(SensorEntity):
    """Samsung appliance power consumption timestamp sensor."""

    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        status_cache: SmartThingsStatusCache,
        smartthings_device_id: str,
        device_name: str,
        report_path: StatusPath,
        field: TimestampField,
    ) -> None:
        """Initialize the sensor."""
        self.status_cache = status_cache
        self.smartthings_device_id = smartthings_device_id
        self.report_path = report_path
        self.field = field
        self._attr_name = field.name
        self._attr_unique_id = f"{smartthings_device_id}_{field.unique_suffix}"
        self._attr_device_info = DeviceInfo(
            identifiers={("smartthings", smartthings_device_id)},
            name=device_name,
        )
        self._attr_native_value = None
        self._attr_extra_state_attributes = {}

    async def async_update(self) -> None:
        """Fetch current SmartThings power consumption status."""
        status = await self.status_cache.async_get_status()
        _report_path, report, attrs = _power_consumption_report(status, self.report_path)
        self._attr_native_value = _timestamp_value(report.get(self.field.attribute))
        self._attr_extra_state_attributes = attrs


def _extra_status_paths(status: dict[str, Any]) -> list[StatusPath]:
    """Return safe scalar Samsung-specific status paths."""
    paths: list[StatusPath] = []
    for component, capabilities in status.items():
        if not isinstance(capabilities, dict):
            continue
        for capability, attributes in capabilities.items():
            if not isinstance(attributes, dict):
                continue
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


def _power_consumption_sensors(
    status_cache: SmartThingsStatusCache,
    smartthings_device_id: str,
    device_name: str,
    report_path: StatusPath,
    report: dict[str, Any],
) -> list[SensorEntity]:
    """Create sensors for fields present in Samsung's power consumption report."""
    entities: list[SensorEntity] = []
    for attribute, field in POWER_CONSUMPTION_NUMERIC_FIELDS.items():
        if _numeric_value(report.get(attribute)) is None:
            continue
        entities.append(
            PowerConsumptionNumericSensor(
                status_cache=status_cache,
                smartthings_device_id=smartthings_device_id,
                device_name=device_name,
                report_path=report_path,
                field=field,
            )
        )
    for attribute, field in POWER_CONSUMPTION_TIMESTAMP_FIELDS.items():
        if _timestamp_value(report.get(attribute)) is None:
            continue
        entities.append(
            PowerConsumptionTimestampSensor(
                status_cache=status_cache,
                smartthings_device_id=smartthings_device_id,
                device_name=device_name,
                report_path=report_path,
                field=field,
            )
        )
    return entities


def _power_consumption_report(
    status: dict[str, Any], path: StatusPath | None = None
) -> tuple[StatusPath, dict[str, Any], dict[str, Any]]:
    """Return Samsung power consumption report and attributes."""
    if path is None:
        path = _power_consumption_path(status)
    if path is None:
        return (
            StatusPath("main", POWER_CONSUMPTION_CAPABILITY, POWER_CONSUMPTION_ATTRIBUTE),
            {},
            {},
        )
    state = (
        status.get(path.component, {})
        .get(path.capability, {})
        .get(path.attribute)
    )
    value = _state_value(state)
    if not isinstance(value, dict):
        return path, {}, {}

    attrs = {
        key: val
        for key, val in value.items()
        if key
        not in {
            *POWER_CONSUMPTION_NUMERIC_FIELDS,
            *POWER_CONSUMPTION_TIMESTAMP_FIELDS,
        }
    }
    attrs["smartthings_component"] = path.component
    timestamp = _state_timestamp(state)
    if timestamp is not None:
        attrs["smartthings_timestamp"] = str(timestamp)
    return path, value, attrs


def _power_consumption_path(status: dict[str, Any]) -> StatusPath | None:
    """Find the component path for Samsung power consumption."""
    for component, capabilities in status.items():
        if not isinstance(capabilities, dict):
            continue
        attributes = capabilities.get(POWER_CONSUMPTION_CAPABILITY)
        if not isinstance(attributes, dict):
            continue
        if POWER_CONSUMPTION_ATTRIBUTE in attributes:
            return StatusPath(
                str(component),
                POWER_CONSUMPTION_CAPABILITY,
                POWER_CONSUMPTION_ATTRIBUTE,
            )
    return None


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
        unit = _state_unit(state)
        timestamp = _state_timestamp(state)
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


def _state_timestamp(state: Any) -> Any:
    """Return a SmartThings state timestamp."""
    if state is None:
        return None
    return getattr(
        state,
        "timestamp",
        state.get("timestamp") if isinstance(state, dict) else None,
    )


def _state_unit(state: Any) -> Any:
    """Return a SmartThings state unit."""
    if state is None:
        return None
    return getattr(state, "unit", state.get("unit") if isinstance(state, dict) else None)


def _numeric_value(value: Any) -> float | None:
    """Return a numeric value from SmartThings payload data."""
    if value in (None, "") or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _scaled_numeric_value(value: Any, scale: float) -> float | None:
    """Return a scaled numeric value with stable precision."""
    numeric = _numeric_value(value)
    if numeric is None:
        return None
    return round(numeric * scale, 6)


def _timestamp_value(value: Any):
    """Return a parsed timestamp from SmartThings payload data."""
    if not isinstance(value, str):
        return None
    return dt_util.parse_datetime(value)
