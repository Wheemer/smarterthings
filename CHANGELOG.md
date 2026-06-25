# Changelog

## 0.3.1

- Trim SmarterThings back to user-facing entities: range clock sync button and appliance power/energy repair.
- Remove clock sync status sensors from the planned entity surface.
- Remove generic Samsung diagnostic sensors and technical energy report detail sensors from the planned entity surface.
- Only create primary replacement power and energy sensors when the matching official SmartThings entity is missing, unavailable, unknown, or stale.
- Automatically disable stale official SmartThings power and energy entities while preserving their original entity ids.
- Let SmarterThings replacement entities use Home Assistant's normal suffixed entity ids with clean friendly names.
- Use recent entity history when detecting stale official appliance power and energy sensors.
- Disable official SmartThings second-cavity range entities when the reported second cavity has no meaningful state.

## 0.3.0

- Fix sensor setup for appliances that expose Samsung `powerConsumptionReport`.
- Add per-device SmartThings status caching so extra appliance sensors share cloud fetches during the same update burst.
- Scan all SmartThings components for Samsung power consumption reports instead of assuming `main`.
- Add Samsung interval, power-energy, persisted-energy, saved-energy, and report-window timestamp sensors when present.
- Keep Samsung power and energy replacement sensors attached to the existing SmartThings appliance device.

## 0.2.1

- Rename repository, integration domain, and service namespace to SmarterThings.

## 0.2.0

- Rename integration to SmarterThings.
- Add native clock sync button entity.
- Add clock sync status sensors.
- Add read-only Samsung appliance diagnostic sensors.
- Add replacement Samsung appliance power and energy sensors from `powerConsumptionReport`.
- Add optional clock sync automation blueprint.

## 0.1.0

- Initial release.
- Add UI setup flow.
- Add configurable startup and nightly range-clock sync.
- Add manual clock sync service.
