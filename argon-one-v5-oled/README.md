# Argon ONE OLED Display Add-on for Home Assistant

A hardened Raspberry Pi 5 / Argon ONE V5 Industria OLED app with three selectable display modes:

- **Current** — the existing rotating system-status screens.
- **Ambient** — generative art driven by Home Assistant state.
- **Character** — a small house character whose expression reflects the home.

All modes can use the same priority system: **urgent faults → one contextual fact → normal selected mode**.

## Display modes

### Current

Set:

```yaml
mode: current
```

This preserves the existing rotation configured by `screen_list`:

- `clock`
- `hastatus`
- `cpu`
- `fan`
- `ram`
- `storage`
- `ip`
- `uptime`
- optional `logo`, `qr`, `temp`

### Ambient

Set:

```yaml
mode: ambient
ambient_scene: auto
```

`auto` selects a living monochrome scene from `landscape`, `stars`, `weather`, `waves`, `city`, `plant`, and `particles`. You can force any one of those scene names instead.

Available Home Assistant state influences the output. Examples include time of day, weather, indoor/outdoor temperature, occupancy, lights and motion/presence. Missing entity types are simply ignored.

### Character

Set:

```yaml
mode: character
```

The character can sleep when the house is quiet at night, react to arrivals, carry an umbrella in wet weather, sweat when the Pi/home is warm, and become annoyed/confused when a fault needs attention.

Urgent and contextual interruptions become character expressions where possible instead of replacing the character with the standard text alert screen.

## Interruptions

Normal display output can be interrupted by:

1. **Urgent** — existing `faults.py` faults, highest priority.
2. **Contextual** — one currently relevant fact, shown briefly.
3. **Normal** — returns to the selected Current/Ambient/Character mode.

Example contextual facts include an arrival, wet weather, unusually warm/cold indoor temperature, a warm Pi, occupancy, late-night lights or current weather. Only the highest-ranked fact is shown, rather than cycling through them.

Both layers are configurable:

```yaml
contextual_interruptions: true
urgent_interruptions: true
contextual_duration: 8
contextual_interval: 300
```

## Home Assistant polling

Home Assistant entity state is read through the official Core API proxy with a GET-only client.

```yaml
ha_refresh_seconds: 60
```

The default is one entity-state snapshot every 60 seconds; the allowed range is 30–600 seconds. Failed reads retry after 10 seconds. This is independent of the one-second OLED animation/local-metric loop.

Existing Supervisor data remains cached separately: ordinary info for 60 seconds and backups for 5 minutes.

## Configuration

Example:

```yaml
mode: ambient
ambient_scene: auto
contextual_interruptions: true
urgent_interruptions: true
contextual_duration: 8
contextual_interval: 300
ha_refresh_seconds: 60

temp_unit: C
switch_duration: 30
screen_list: "clock hastatus cpu fan ram storage ip uptime"
debug_logging: false
show_credits: true

cpu_temp_alert_c: 80
fan_min_temp_c: 55
backup_max_age_hours: 48
storage_min_free_percent: 10
```

| Option | Default | Description |
|---|---|---|
| `mode` | `current` | `current`, `ambient`, or `character` |
| `ambient_scene` | `auto` | `auto`, `landscape`, `stars`, `weather`, `waves`, `city`, `plant`, or `particles` |
| `contextual_interruptions` | `true` | Allow brief relevance-ranked facts to interrupt normal display output |
| `urgent_interruptions` | `true` | Allow existing faults to supersede all other output |
| `contextual_duration` | `8` | Seconds a contextual fact remains on screen (3–60) |
| `contextual_interval` | `300` | Minimum seconds between contextual interruptions (30–3600) |
| `ha_refresh_seconds` | `60` | Home Assistant entity-state refresh interval (30–600) |
| `temp_unit` | `C` | Display local temperature as C or F |
| `switch_duration` | `30` | Seconds per screen in Current mode |
| `screen_list` | default rotation | Space-separated Current-mode screens |
| `debug_logging` | `false` | Verbose troubleshooting logs |
| `show_credits` | `true` | Show version/attribution splash at startup |
| `cpu_temp_alert_c` | `80` | HIGH TEMP threshold in Celsius |
| `fan_min_temp_c` | `55` | Temperature above which a detected fan is expected to be running |
| `backup_max_age_hours` | `48` | OLD BACKUP threshold |
| `storage_min_free_percent` | `10` | LOW STORAGE threshold for the real host data partition |

## Faults

The existing fault engine is unchanged. With urgent interruptions enabled, priority is:

1. HIGH TEMP
2. FAN STOPPED
3. NO BACKUP / OLD BACKUP
4. LOW STORAGE
5. HA STATUS unavailable
6. pending Supervisor/Core UPDATES

## Fan behaviour

This app **never controls the Raspberry Pi 5 fan**. It only reads the kernel `hwmon` RPM/PWM/status data. The native firmware/kernel fan policy remains authoritative.

## Permissions

Version 2.2 keeps the existing narrow security model:

- only `/dev/i2c-1` is exposed
- `gpio: false`
- no `/config`, `/ssl`, `/share` or `/backup` volume mapping
- AppArmor remains enforced
- `hassio_role: backup` remains unchanged; no `manager`/`admin`
- no reboot/shutdown or other host-control paths
- no service calls or mutating HTTP methods

The only functional permission addition is `homeassistant_api: true`, required to GET Home Assistant entity state. `home_context.py` only calls `http://supervisor/core/api/states` and is regression-tested to contain no POST/PUT/PATCH/DELETE or service-call path.

AppArmor only adds read permission for the three new bundled code modules; it does not add any new host path, device, capability or write access.

## Hardware requirements

- Raspberry Pi 5 / aarch64 Home Assistant OS
- Argon ONE V5 Industria 128x64 SSD1306 OLED
- I2C bus 1 enabled (`/dev/i2c-1`)

## Architecture

- `argon_oled.py` — main loop and mode orchestration
- `system_info.py` — local system metrics and read-only fan `hwmon`
- `supervisor_api.py` — cached GET-only Supervisor client
- `home_context.py` — cached GET-only Home Assistant state client
- `faults.py` — urgent fault evaluator
- `interruptions.py` — urgent/context/normal arbitration
- `screens.py` — existing status and alert screens
- `visual_modes.py` — ambient scenes, contextual display and character

## License / attribution

MIT licensed. See the repository-level README, `LICENSE`, and `THIRD_PARTY_NOTICES.md` for full attribution and upstream history.
