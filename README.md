# SmarterThings

Home Assistant custom integration for exposing useful Samsung SmartThings appliance features that the built-in SmartThings integration does not currently surface.

The current release focuses on Samsung ranges/ovens and appliance diagnostics:

- A native button entity to sync the range clock.
- Last clock sync status sensors.
- Replacement Samsung appliance power and energy sensors for devices that expose `powerConsumptionReport`.
- Extra Samsung appliance energy report sensors for interval, saved, persisted, and report-window values when Samsung exposes them.
- Configurable startup and nightly clock sync.
- A reusable automation blueprint for users who prefer automation-managed scheduling.
- Read-only diagnostic sensors for Samsung-specific SmartThings appliance status attributes.

The longer-term goal is to expose the missing-but-useful Samsung appliance controls and diagnostics for ranges, refrigerators, washers, dryers, and similar SmartThings appliances without turning the integration into an unsafe raw command launcher.

## Requirements

- Home Assistant with the built-in SmartThings integration already configured.
- Samsung SmartThings appliances visible in Home Assistant.

SmarterThings reuses Home Assistant's existing SmartThings OAuth token. It does not require a SmartThings personal access token.

## Installation

### HACS custom repository

1. Open HACS.
2. Add this repository as a custom integration repository.
3. Install **SmarterThings**.
4. Restart Home Assistant.
5. Go to **Settings → Devices & services → Add integration**.
6. Search for **SmarterThings**.

### Manual

Copy `custom_components/smarterthings` into your Home Assistant `custom_components` directory, then restart Home Assistant.

## Setup

During setup, choose a Home Assistant entity that belongs to your Samsung SmartThings range, such as:

```text
sensor.range_operating_state
```

The integration resolves the underlying Home Assistant device and SmartThings device ID from that entity. Other Samsung SmartThings appliance diagnostics are discovered from the loaded SmartThings devices and attached to their existing Home Assistant device pages.

## Entities

### Range Clock

SmarterThings creates these entities on the configured range device:

- `button.*_sync_clock`
- `sensor.*_last_clock_sync`
- `sensor.*_clock_sync_status`

The clock sync command uses Samsung's known SmartThings execute endpoint:

```yaml
component: main
capability: execute
command: execute
arguments:
  - /configuration/vs/0
  - x.com.samsung.da.currentTime: "YYYY-MM-DDTHH:MM:SS"
```

Samsung does not appear to expose the appliance's displayed clock as a readable status attribute, so the integration can send the sync command but cannot read the display clock back.

### Appliance Diagnostics

SmarterThings also creates diagnostic sensors from Samsung-specific SmartThings status attributes when they are scalar values and safe to display. These are attached to the same Home Assistant device as the source SmartThings appliance.

Examples include values under:

- `samsungce.*`
- `custom.*`
- `sec.*`
- `remoteControlStatus`

This is intentionally read-only in the first broad appliance pass.

### Appliance Power

For Samsung appliances that expose `powerConsumptionReport`, SmarterThings creates replacement sensors attached to the appliance device:

- `sensor.*_samsung_power`
- `sensor.*_samsung_energy`
- `sensor.*_samsung_interval_energy`
- `sensor.*_samsung_power_energy`
- `sensor.*_samsung_persisted_energy`
- `sensor.*_samsung_energy_saved`
- `sensor.*_samsung_persisted_saved_energy`
- `sensor.*_samsung_energy_report_start`
- `sensor.*_samsung_energy_report_end`

SmarterThings scans all SmartThings components for the Samsung report instead of assuming it is always under `main`. Energy-like values are converted from Samsung's Wh-style payload values to kWh for Home Assistant.

These are intended for appliances where the built-in SmartThings power entities are missing, stale, stuck, or otherwise not useful. Entity availability is model-dependent. For example, some Samsung ranges do not expose `powerConsumptionReport` at all, so SmarterThings will not create power or energy sensors for those ranges.

## Options

The integration options let you configure:

- Startup sync enabled or disabled.
- Startup sync delay in minutes.
- Nightly sync time.
- Target range entity.

Defaults:

- Startup sync: enabled
- Startup sync delay: 15 minutes
- Nightly sync time: 00:05

## Manual Service

Call:

```yaml
action: smarterthings.sync_time
data: {}
```

The service syncs all configured range clock targets.

## Blueprint

The repository includes an optional automation blueprint:

```text
blueprints/automation/smarterthings_clock_sync.yaml
```

Use it when you want Home Assistant automations to press the clock sync button on startup and on a daily schedule instead of relying on the integration's built-in scheduler.

## Safety

SmarterThings does not expose a generic arbitrary SmartThings command service. Controls should be added as explicit, reviewed entities with clear behavior.

## Development Status

Early release. The initial scope is:

- Samsung range clock sync.
- Safe Samsung appliance diagnostics.
- Replacement Samsung appliance power and energy sensors.

Future work may add model-specific controls for refrigerators, washers, dryers, and ranges where the SmartThings command surface can be verified.

## License

MIT
