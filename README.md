# KNX Programming Mode Watcher

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

Home Assistant custom integration that detects KNX devices in programming
mode and exposes them as entities + events so you can fire push
notifications, TTS announcements, or any other automation when a device
goes in or out of programming mode.

It reuses the running `xknx` instance owned by HA's built-in KNX
integration — **no extra tunnel, no extra gateway config, no duplicated
credentials**. If you've already got the KNX integration working, this
just bolts on.

## Install via HACS (custom repository)

1. In HACS → **Integrations** → ⋯ menu → **Custom repositories**.
2. Add `https://github.com/edmondharty/ha-knx-progmode` with category
   **Integration**.
3. Search for **"KNX Programming Mode Watcher"** in HACS and install.
4. Restart Home Assistant.
5. Settings → **Devices & Services** → **Add Integration** → search for
   "KNX Programming Mode Watcher". No fields to fill — defaults are fine.
6. Find the **`switch.knx_programming_mode_scanning`** entity and turn it
   on when you want the integration to scan the bus.

> **Requires** Home Assistant's built-in KNX integration to be configured
> and running.

## Manual install

Copy `custom_components/knx_progmode/` from this repo into your HA
`config/custom_components/` directory, then continue from step 4 above.

## Entities

| Entity | Purpose |
|---|---|
| `switch.knx_programming_mode_scanning` | **Off by default.** Turn on to start scanning the bus. State is restored across restarts. |
| `sensor.knx_devices_in_programming_mode` | State = number of devices currently in programming mode. Attribute `devices` is the full list of dicts (see fields below); attribute `addresses` is just the list of individual addresses; attribute `scanning` mirrors the switch. |
| `binary_sensor.knx_programming_mode_active` | On whenever the count > 0. Use this for plain state triggers. |

There are deliberately **no per-device permanent entities** — only
currently-in-programming-mode devices appear, and the set is cleared when
scanning is turned off.

## Events

Fired on `hass.bus`:

- `knx_progmode_entered` — when a new individual address starts responding
  to programming-mode broadcasts.
- `knx_progmode_left` — when an address stops responding. Carries the
  cached identify/project data from when it entered, plus `left_at`.

### Payload fields

Every payload always contains the full set of keys; missing data is `null`.

| Field | Source | Notes |
|---|---|---|
| `address` | scan | Individual address, e.g. `"1.1.5"` |
| `entered_at` / `left_at` | scan | ISO timestamps |
| `display_name` | hybrid | TTS-friendly. Prefers ETS `project_name`, then `manufacturer_name + product_name`, falls back to `address` |
| `mask`, `mask_family` | bus identify | e.g. `"0x07B0"`, `"TP1 System B"` |
| `manufacturer_id`, `manufacturer_name` | bus identify | Read from the device's property table |
| `order_info` | bus identify | Product order code |
| `serial` | bus identify | Unique 6-byte serial, formatted `aabb:ccddeeff` |
| `project_name` | ETS project | The label you gave the device in ETS |
| `project_description` | ETS project | Free text from ETS |
| `project_manufacturer_name` | ETS project | Full vendor name string |
| `project_product_name` | ETS project | Catalog product, e.g. `"AKK-0816.03"` |
| `project_hardware_name` | ETS project | Hardware variant |
| `project_application_program` | ETS project | Application program name |
| `project_area`, `project_line` | ETS project | Topology |

Project fields require the `.knxproj` to be imported into HA's KNX
integration. Bus-identify fields require the `identify` option (default
on) and add ~1–2 seconds of bus traffic per new device.

## Options

Settings → Devices & Services → KNX Programming Mode Watcher →
**Configure**:

- **Scan window** (`timeout`, default `3.0` s) — how long each
  `IndividualAddressRead` listens for replies. KNX spec is 3 s.
- **Idle gap between scans** (`interval`, default `1.0` s) — sleep
  between scan cycles.
- **Identify on entry** (`identify`, default **on**) — read mask version,
  manufacturer, order info, and serial when a device first appears.

## Example automations

### Push notification when a specific device enters programming mode

```yaml
alias: "Notify when 1.1.5 enters programming mode"
trigger:
  - platform: event
    event_type: knx_progmode_entered
    event_data:
      address: "1.1.5"
action:
  - service: notify.mobile_app_my_phone
    data:
      title: "KNX programming mode"
      message: "{{ trigger.event.data.display_name }} is in programming mode."
```

### TTS on any device entering or leaving

```yaml
alias: "Announce KNX programming-mode changes"
trigger:
  - platform: event
    event_type:
      - knx_progmode_entered
      - knx_progmode_left
action:
  - service: tts.cloud_say
    data:
      entity_id: media_player.living_room
      message: >-
        {{ trigger.event.data.display_name }}
        {{ 'entered' if trigger.event.event_type == 'knx_progmode_entered' else 'left' }}
        programming mode.
```

`display_name` is the ETS-given device name when the project is loaded,
otherwise the vendor + product, otherwise the raw individual address — so
the announcement says "Living-room switch actuator" instead of "1.1.5"
without you writing the fallback chain.

### Alert if more than one device is in programming mode at once

```yaml
trigger:
  - platform: numeric_state
    entity_id: sensor.knx_devices_in_programming_mode
    above: 1
action:
  - service: notify.mobile_app_my_phone
    data:
      message: >-
        Multiple KNX devices in programming mode:
        {{ state_attr('sensor.knx_devices_in_programming_mode', 'addresses') | join(', ') }}
```

## How it works

1. While the **scanning** switch is on, the integration sends an
   `IndividualAddressRead` broadcast every `timeout + interval` seconds.
   Only devices currently in programming mode respond.
2. New responders fire `knx_progmode_entered`; missing responders fire
   `knx_progmode_left`.
3. On a new device, it does a connection-oriented read of the device
   descriptor and a few standard properties (manufacturer, order info,
   serial) for the bus-identify fields.
4. It also looks up the individual address in the ETS project that HA's
   KNX integration has loaded — these enrichment fields are free (no bus
   traffic).

## Standalone CLI

The repo also includes `check_programming_mode.py`, a standalone xknx
script that does the same scan + identify outside Home Assistant. Useful
for debugging from a laptop on the same KNX/IP gateway. See
`requirements.txt` for its dependencies.

## Notes

- The scanner reuses HA's `xknx` instance, so the gateway, tunnel
  credentials, and routing settings come from the KNX integration. There
  is no separate gateway config here.
- If the KNX integration isn't loaded yet, setup raises
  `ConfigEntryNotReady` and HA retries automatically.
- Scanning is broadcast-noisy on the bus (one `IndividualAddressRead`
  every ~4 s while on). Turn it off when you're not commissioning.

## License

MIT — see [LICENSE](LICENSE).
