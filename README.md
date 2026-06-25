# SmarterThings

Home Assistant custom integration for exposing useful Samsung SmartThings appliance features that the built-in SmartThings integration does not currently surface.

SmarterThings keeps the surface intentionally small:

- A native button entity to sync the range clock.
- Automatic repair of stale or missing Samsung appliance power and energy sensors.
- Configurable startup and nightly clock sync.
- A reusable automation blueprint for users who prefer automation-managed scheduling.

The longer-term goal is to expose only missing-but-useful Samsung appliance controls and sensors for ranges, refrigerators, washers, dryers, and similar SmartThings appliances without turning the integration into a raw capability dump.

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

The integration resolves the underlying Home Assistant device and SmartThings device ID from that entity. Samsung appliance power repair is discovered from the loaded SmartThings devices and attached to their existing Home Assistant device pages.

## Entities

### Range Clock

SmarterThings creates these entities on the configured range device:

- `button.*_sync_clock`

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

### Appliance Power

For Samsung appliances that expose `powerConsumptionReport`, SmarterThings creates replacement sensors attached to the appliance device when the matching official SmartThings entity is missing, unavailable, unknown, or has not updated for several hours:

- `sensor.*_samsung_power`
- `sensor.*_samsung_energy`

When SmarterThings finds a stale official SmartThings power or energy entity, it disables that official entity, moves it to a backup entity id ending in `_smartthings_original`, and moves the SmarterThings replacement onto the original clean entity id. Working official entities are left alone.

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
- Replacement Samsung appliance power and energy sensors only when the official ones are missing or stale.

Future work may add model-specific controls for refrigerators, washers, dryers, and ranges where the SmartThings command surface can be verified.

## License

MIT
