"""Sensor entities for SmarterThings."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import timedelta
import logging
from time import monotonic
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, UnitOfEnergy, UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from . import RangeClockRuntime, _get_smartthings_client

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(minutes=10)

POWER_CONSUMPTION_CAPABILITY = "powerConsumptionReport"
POWER_CONSUMPTION_ATTRIBUTE = "powerConsumption"
STATUS_CACHE_TTL = 5
STALE_ENTITY_AGE = timedelta(hours=6)


@dataclass(frozen=True)
class StatusPath:
    """One flattened SmartThings status path."""

    component: str
    capability: str
    attribute: str


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
    replacement_kind: str | None = None


@dataclass(frozen=True)
class ReplacementInfo:
    """Official SmartThings entity replacement decision."""

    should_create: bool
    target_entity_id: str | None = None


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
        replacement_kind="power",
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
        replacement_kind="energy",
    ),
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry[RangeClockRuntime],
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensors."""
    entities: list[SensorEntity] = []

    for smartthings_entry in hass.config_entries.async_entries("smartthings"):
        data = smartthings_entry.runtime_data
        for device_id, full_device in data.devices.items():
            device_name = full_device.device.label or full_device.device.name
            ha_device_id = _ha_device_id(hass, device_id)
            status_cache = SmartThingsStatusCache(hass, device_id)
            report_path, report, _attrs = _power_consumption_report(full_device.status)
            if report:
                replacements = _replacement_plan(hass, ha_device_id)
                entities.extend(
                    _power_consumption_sensors(
                        status_cache=status_cache,
                        smartthings_device_id=device_id,
                        device_name=device_name,
                        report_path=report_path,
                        report=report,
                        replacements=replacements,
                    )
                )

    async_add_entities(entities)


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
        replacement: ReplacementInfo,
    ) -> None:
        """Initialize the sensor."""
        self.status_cache = status_cache
        self.smartthings_device_id = smartthings_device_id
        self.report_path = report_path
        self.field = field
        self.replacement = replacement
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

    async def async_added_to_hass(self) -> None:
        """Take over stale official SmartThings entity id if requested."""
        if self.replacement.target_entity_id is None:
            return
        _replace_official_entity_id(
            self.hass,
            stale_entity_id=self.replacement.target_entity_id,
            replacement_entity_id=self.entity_id,
        )


def _power_consumption_sensors(
    status_cache: SmartThingsStatusCache,
    smartthings_device_id: str,
    device_name: str,
    report_path: StatusPath,
    report: dict[str, Any],
    replacements: dict[str, ReplacementInfo],
) -> list[SensorEntity]:
    """Create sensors for fields present in Samsung's power consumption report."""
    entities: list[SensorEntity] = []
    for attribute, field in POWER_CONSUMPTION_NUMERIC_FIELDS.items():
        if _numeric_value(report.get(attribute)) is None:
            continue
        replacement = ReplacementInfo(should_create=True)
        if field.replacement_kind is not None:
            replacement = replacements.get(
                field.replacement_kind, ReplacementInfo(should_create=False)
            )
            if not replacement.should_create:
                continue
        entities.append(
            PowerConsumptionNumericSensor(
                status_cache=status_cache,
                smartthings_device_id=smartthings_device_id,
                device_name=device_name,
                report_path=report_path,
                field=field,
                replacement=replacement,
            )
        )
    return entities


def _ha_device_id(hass: HomeAssistant, smartthings_device_id: str) -> str | None:
    """Return the Home Assistant device id for a SmartThings device."""
    device_entry = dr.async_get(hass).async_get_device(
        identifiers={("smartthings", smartthings_device_id)}
    )
    return device_entry.id if device_entry is not None else None


def _replacement_plan(
    hass: HomeAssistant, ha_device_id: str | None
) -> dict[str, ReplacementInfo]:
    """Return official SmartThings measurements that should be replaced."""
    if ha_device_id is None:
        return {
            "power": ReplacementInfo(should_create=True),
            "energy": ReplacementInfo(should_create=True),
        }

    registry = er.async_get(hass)
    replacements: dict[str, ReplacementInfo] = {}
    official = {
        kind: _official_measurement_entity(registry, ha_device_id, kind)
        for kind in ("power", "energy")
    }

    for kind, entity_id in official.items():
        if entity_id is None:
            replacements[kind] = ReplacementInfo(should_create=True)
        elif _entity_is_stale_or_unavailable(hass, entity_id):
            replacements[kind] = ReplacementInfo(
                should_create=True, target_entity_id=entity_id
            )

    return replacements


def _official_measurement_entity(
    registry: er.EntityRegistry, ha_device_id: str, kind: str
) -> str | None:
    """Find an official SmartThings measurement entity on the appliance."""
    for entry in registry.entities.values():
        if (
            entry.platform != "smartthings"
            or entry.device_id != ha_device_id
            or not entry.entity_id.startswith("sensor.")
            or entry.disabled_by is not None
        ):
            continue

        haystack = " ".join(
            str(value or "").lower()
            for value in (
                entry.entity_id,
                getattr(entry, "original_name", None),
                getattr(entry, "name", None),
                getattr(entry, "translation_key", None),
                entry.unique_id,
            )
        )
        if kind == "power" and "power" in haystack and "energy" not in haystack:
            return entry.entity_id
        if kind == "energy" and "energy" in haystack:
            return entry.entity_id
    return None


def _entity_is_stale_or_unavailable(hass: HomeAssistant, entity_id: str) -> bool:
    """Return true if an official entity should be replaced."""
    state = hass.states.get(entity_id)
    if state is None or state.state in {"unknown", "unavailable"}:
        return True
    if dt_util.utcnow() - state.last_updated > STALE_ENTITY_AGE:
        return True
    return False


def _replace_official_entity_id(
    hass: HomeAssistant, stale_entity_id: str, replacement_entity_id: str
) -> None:
    """Disable stale official entity and move replacement onto its entity id."""
    if stale_entity_id == replacement_entity_id:
        return

    registry = er.async_get(hass)
    stale_entry = registry.async_get(stale_entity_id)
    replacement_entry = registry.async_get(replacement_entity_id)
    if stale_entry is None or replacement_entry is None:
        return
    if stale_entry.disabled_by is not None:
        return

    backup_entity_id = _backup_entity_id(registry, stale_entity_id)
    try:
        registry.async_update_entity(
            stale_entity_id,
            new_entity_id=backup_entity_id,
            disabled_by=er.RegistryEntryDisabler.INTEGRATION,
        )
        registry.async_update_entity(
            replacement_entity_id,
            new_entity_id=stale_entity_id,
        )
    except (KeyError, ValueError) as err:
        _LOGGER.warning(
            "Could not replace stale SmartThings entity %s with %s: %s",
            stale_entity_id,
            replacement_entity_id,
            err,
        )


def _backup_entity_id(registry: er.EntityRegistry, entity_id: str) -> str:
    """Return an unused backup entity id for a disabled official entity."""
    domain, object_id = entity_id.split(".", 1)
    base = f"{domain}.{object_id}_smartthings_original"
    candidate = base
    index = 2
    while registry.async_get(candidate) is not None:
        candidate = f"{base}_{index}"
        index += 1
    return candidate


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
