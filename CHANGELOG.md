# Changelog

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
