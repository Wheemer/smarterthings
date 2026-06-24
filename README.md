# Samsung Range Clock Sync

Home Assistant custom integration for keeping a Samsung SmartThings range clock in sync with Home Assistant's local time.

This integration reuses Home Assistant's built-in SmartThings integration and its OAuth token. It does not require a SmartThings personal access token.

## Features

- Config flow setup from the Home Assistant UI.
- Select any existing SmartThings entity that belongs to the target range.
- Sync the range clock shortly after Home Assistant starts.
- Sync the range clock daily at a configurable time.
- Manual `smartthings_range_clock.sync_time` service.
- Sends the known Samsung clock command through SmartThings Cloud:

```yaml
component: main
capability: execute
command: execute
arguments:
  - /configuration/vs/0
  - x.com.samsung.da.currentTime: "YYYY-MM-DDTHH:MM:SS"
```

## Requirements

- Home Assistant with the built-in SmartThings integration already configured.
- A Samsung range/oven visible in Home Assistant through SmartThings.

## Installation

### HACS custom repository

1. Open HACS.
2. Add this repository as a custom integration repository.
3. Install **Samsung Range Clock Sync**.
4. Restart Home Assistant.
5. Go to **Settings → Devices & services → Add integration**.
6. Search for **Samsung Range Clock Sync**.

### Manual

Copy `custom_components/smartthings_range_clock` into your Home Assistant `custom_components` directory, then restart Home Assistant.

## Setup

During setup, choose a Home Assistant entity that belongs to your SmartThings range, such as:

```text
sensor.range_operating_state
```

The integration resolves the underlying Home Assistant device and SmartThings device ID from that entity.

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
action: smartthings_range_clock.sync_time
data: {}
```

The service syncs all configured range clocks.

## Notes

Samsung does not appear to expose the range's displayed clock as a readable SmartThings status attribute. This integration can send a clock sync command, but it cannot verify the displayed clock by reading it back from the appliance.

The command used by this integration is an undocumented Samsung SmartThings appliance command. It is known to work on some Samsung ranges/ovens, but model and region support may vary.

## Development Status

Early release. The first goal is reliable range clock sync. Additional Samsung appliance diagnostics or sensors may be added later if they can be exposed cleanly and safely.

## License

MIT

