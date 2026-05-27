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
6. Find the **`switch.knx_programming_mode_watcher_scanning`** entity and
   turn it on when you want the integration to scan the bus.

> **Requires** Home Assistant's built-in KNX integration to be configured
> and running.

## Manual install

Copy `custom_components/knx_progmode/` from this repo into your HA
`config/custom_components/` directory, then continue from step 4 above.

## Entities

All three entities are grouped under a single device, "KNX Programming
Mode Watcher", visible at Settings → Devices & Services.

| Entity | Purpose |
|---|---|
| `switch.knx_programming_mode_watcher_scanning` | **Off by default.** Turn on to start scanning the bus. State is restored across restarts. |
| `sensor.knx_programming_mode_watcher_devices_in_programming_mode` | State = number of devices currently in programming mode. Attribute `devices` is the full list of dicts (see fields below); attribute `addresses` is just the list of individual addresses; attribute `scanning` mirrors the switch. |
| `binary_sensor.knx_programming_mode_watcher_programming_mode_active` | On whenever the count > 0. Use this for plain state triggers. |

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

### Push notification on every entry/exit with the full payload

This is the most useful general-purpose automation: one rule that fires for
both `entered` and `left` events, sends a notification to any mobile app,
collapses to a single banner per device (the second notification updates
the first in place), and includes every populated field in the body.

Replace `notify.mobile_app_YOUR_PHONE` with your own mobile app notify
service.

```yaml
alias: "KNX programming mode → push notification"
description: >-
  Push notification when a KNX device enters or leaves programming mode.
  Includes ETS project name/area/product and bus-identify mask/manufacturer/order/serial.
mode: parallel
max: 20
trigger:
  - platform: event
    event_type:
      - knx_progmode_entered
      - knx_progmode_left
action:
  - variables:
      d: "{{ trigger.event.data }}"
      verb: >-
        {{ 'entered' if trigger.event.event_type == 'knx_progmode_entered'
           else 'left' }}
  - service: notify.mobile_app_YOUR_PHONE
    data:
      title: "KNX {{ d.display_name }} {{ verb }} programming mode"
      message: >-
        {% set fields = [
          ('Address', d.address),
          ('Entered', d.entered_at),
          ('Left', d.left_at),
          ('ETS name', d.project_name),
          ('Description', d.project_description),
          ('Area', d.project_area),
          ('Line', d.project_line),
          ('Manufacturer (ETS)', d.project_manufacturer_name),
          ('Product (ETS)', d.project_product_name),
          ('Hardware (ETS)', d.project_hardware_name),
          ('Application', d.project_application_program),
          ('Mask', (d.mask ~ ' (' ~ d.mask_family ~ ')')
                   if d.mask and d.mask_family else d.mask),
          ('Manufacturer (bus)', (d.manufacturer_name ~ ' [id ' ~ d.manufacturer_id|string ~ ']')
                   if d.manufacturer_name and d.manufacturer_id else d.manufacturer_name),
          ('Order info', d.order_info),
          ('Serial', d.serial),
        ] %}{% for label, value in fields if value %}{{ label }}: {{ value }}
        {% endfor %}
      data:
        # iOS (mobile_app on iPhone/iPad). Safe to omit on Android.
        push:
          interruption-level: time-sensitive
          thread-id: "knx-progmode-{{ d.address }}"
        group: "knx-programming-mode"
        # Replace the "entered" notification with "left" for the same device:
        tag: "knx-progmode-{{ d.address }}"
        url: "homeassistant://navigate/lovelace/0"
```

### Push notification only when a specific device enters programming mode

```yaml
alias: "Notify when 1.1.5 enters programming mode"
trigger:
  - platform: event
    event_type: knx_progmode_entered
    event_data:
      address: "1.1.5"
action:
  - service: notify.mobile_app_YOUR_PHONE
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
    entity_id: sensor.knx_programming_mode_watcher_devices_in_programming_mode
    above: 1
action:
  - service: notify.mobile_app_YOUR_PHONE
    data:
      message: >-
        Multiple KNX devices in programming mode:
        {{ state_attr('sensor.knx_programming_mode_watcher_devices_in_programming_mode', 'addresses') | join(', ') }}
```

## Sample dashboard

A single Lovelace view that shows the controls, the count, and a live
list of every device currently in programming mode with its full data.
No HACS cards required — pure built-in `tile`, `markdown`, and `sections`.

Settings → Dashboards → **+ Add Dashboard** → New dashboard from scratch
→ ⋮ menu → Raw configuration editor → paste:

```yaml
title: KNX Programming Mode
views:
  - title: Live
    path: live
    icon: mdi:cog-sync
    type: sections
    max_columns: 2
    sections:
      - type: grid
        cards:
          - type: heading
            heading: Status
            heading_style: subtitle
          - type: tile
            entity: switch.knx_programming_mode_watcher_scanning
            name: Scanning
            features:
              - type: toggle
          - type: tile
            entity: sensor.knx_programming_mode_watcher_devices_in_programming_mode
            name: Devices in programming mode
          - type: tile
            entity: binary_sensor.knx_programming_mode_watcher_programming_mode_active
            name: Any device active
      - type: grid
        cards:
          - type: heading
            heading: Currently in programming mode
            heading_style: subtitle
          - type: markdown
            content: |-
              {% set devices = state_attr('sensor.knx_programming_mode_watcher_devices_in_programming_mode', 'devices') or [] %}
              {% if devices | count == 0 %}
              *No devices currently in programming mode.*
              {% if not is_state('switch.knx_programming_mode_watcher_scanning', 'on') %}

              Scanning is **off** — flip the **Scanning** switch above to start detecting devices on the bus.
              {% else %}

              Scanning is **on**. Put a device into programming mode to see it appear here within a few seconds.
              {% endif %}
              {% else %}
              {% for d in devices %}
              ### {{ loop.index }}. {{ d.display_name }}
              **Address:** `{{ d.address }}`{% if d.entered_at %} · **Entered:** {{ d.entered_at }}{% endif %}

              {% set has_project = d.project_name or d.project_description or d.project_area or d.project_line or d.project_manufacturer_name or d.project_product_name or d.project_hardware_name or d.project_application_program %}
              {% if has_project %}**ETS project**
              {% if d.project_name %}- Name: {{ d.project_name }}
              {% endif %}{% if d.project_description %}- Description: {{ d.project_description }}
              {% endif %}{% if d.project_manufacturer_name %}- Manufacturer: {{ d.project_manufacturer_name }}
              {% endif %}{% if d.project_product_name %}- Product: {{ d.project_product_name }}
              {% endif %}{% if d.project_hardware_name %}- Hardware: {{ d.project_hardware_name }}
              {% endif %}{% if d.project_application_program %}- Application: {{ d.project_application_program }}
              {% endif %}{% if d.project_area or d.project_line %}- Topology: area {{ d.project_area or '?' }} / line {{ d.project_line or '?' }}
              {% endif %}
              {% endif %}
              {% set has_bus = d.mask or d.manufacturer_name or d.order_info or d.serial %}
              {% if has_bus %}**Bus identify**
              {% if d.mask %}- Mask: `{{ d.mask }}`{% if d.mask_family %} ({{ d.mask_family }}){% endif %}
              {% endif %}{% if d.manufacturer_name %}- Manufacturer: {{ d.manufacturer_name }}{% if d.manufacturer_id %} (id {{ d.manufacturer_id }}){% endif %}
              {% endif %}{% if d.order_info %}- Order info: `{{ d.order_info }}`
              {% endif %}{% if d.serial %}- Serial: `{{ d.serial }}`
              {% endif %}
              {% endif %}
              ---
              {% endfor %}
              {% endif %}
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

## Changelog

### v0.1.1

- All three entities now belong to a single device, **"KNX Programming
  Mode Watcher"**, visible in Settings → Devices & Services. This also
  changes the entity IDs new installs get — they are now prefixed with
  `knx_programming_mode_watcher_` (e.g.
  `switch.knx_programming_mode_watcher_scanning`).
- **Existing installations upgrading from v0.1.0** will keep their old
  short entity IDs (`switch.scanning`, `sensor.devices_in_programming_mode`,
  `binary_sensor.programming_mode_active`) because HA preserves the
  registry binding. To pick up the new IDs:
  1. Settings → Devices & Services → KNX Programming Mode Watcher →
     ⋮ menu → **Delete**.
  2. Re-add the integration from the same page.
  3. Update any dashboards / automations that reference the old IDs.

### v0.1.0

Initial release.

## License

MIT — see [LICENSE](LICENSE).
