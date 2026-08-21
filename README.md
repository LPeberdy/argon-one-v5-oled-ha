# Argon ONE OLED Display — Home Assistant Add-on Repository

A Home Assistant OS add-on for the 128x64 SSD1306 OLED in an **Argon ONE V5 Industria** case on Raspberry Pi 5.

Version 2.2 adds three selectable display personalities while keeping the hardened, read-only system-monitoring design:

- **Current** — the existing rotating system-status screens.
- **Ambient** — generative monochrome art driven by Home Assistant state.
- **Character** — a small house creature whose expression reflects the home.

All three can use the same interruption hierarchy: **urgent faults → one contextual fact → normal selected mode**.

## Install

1. In Home Assistant, open **Settings → Apps → App store → ⋮ → Repositories**.
2. Add this repository's URL.
3. Install **Argon ONE OLED Display**.
4. Ensure I2C is enabled and `/dev/i2c-1` exists.
5. Choose a display mode in the app's **Configuration** tab and start the app.

The app keeps the same slug (`argon_one_oled_display`), so 2.2.0 is an in-place update from earlier hardened releases.

## Display modes

### `current`

Preserves the existing rotating screens configured by `screen_list`: clock, HA status, CPU, fan, RAM, storage, IP, uptime, and optional logo/QR screens.

### `ambient`

A continuously evolving monochrome screensaver. With `ambient_scene: auto`, the app chooses between:

- `landscape`
- `stars`
- `weather`
- `waves`
- `city`
- `plant`
- `particles`

The scene reacts to available Home Assistant state such as time of day, weather, indoor/outdoor temperature, people at home, lights and motion/presence. Missing entity types simply remove that input; they do not stop the display.

### `character`

A persistent little house character derived from the same state. It can sleep when the house is quiet at night, wake up when the home is active, react to arrivals, carry an umbrella in wet weather, sweat when the Pi/home is warm, and become annoyed or confused for faults.

Urgent/contextual events are represented primarily as expressions in Character mode rather than replacing it with the standard alert design.

## Interruption hierarchy

The display arbiter has three levels:

1. **Urgent** — the existing `faults.py` faults. These always rank above contextual facts when `urgent_interruptions` is enabled.
2. **Contextual** — a single relevance-ranked current fact, shown briefly rather than as another information carousel.
3. **Normal** — whichever display mode is selected.

Contextual examples include a recent arrival, wet weather, unusually warm/cold indoor temperature, a warm Pi, occupancy, late-night lights, or current weather. Only the highest-ranked current fact is shown.

`contextual_interruptions` and `urgent_interruptions` are independently configurable. Contextual display duration and minimum repeat interval are configurable as well.

## Home Assistant context and polling

Ambient/Character/contextual features use Home Assistant's official Core API proxy and read `/states` with the app's `SUPERVISOR_TOKEN`.

- Successful entity snapshots are cached for **60 seconds by default** (`ha_refresh_seconds`, configurable 30–600s).
- Failed reads are retried after **10 seconds**.
- Recent `person.*` arrival transitions are retained briefly so they remain visible despite the intentionally slow polling cadence.
- Existing Supervisor polling remains separately cached: ordinary Supervisor/Core/network info at 60 seconds and backups at 5 minutes.

The one-second OLED animation/local-metric loop therefore does **not** translate into one-second Home Assistant API traffic.

## Permissions and security model

This remains a least-privilege display app. Version 2.2 adds only the access required to **read Home Assistant entity state**.

| Capability | Setting | Why |
|---|---|---|
| OLED I2C | `/dev/i2c-1` only | Drives the Argon OLED; no broad I2C mapping. |
| GPIO | `gpio: false` | No GPIO button or GPIO writes. |
| Home Assistant config | not mapped | No `/config`, `/ssl`, `/share` or `/backup` host volume access. |
| AppArmor | `apparmor: true` | Enforced; new profile entries only allow read access to the new bundled Python modules. No new host paths/devices/capabilities are granted. |
| Supervisor API | `hassio_api: true`, `hassio_role: backup` | Same narrow role used for read-only status and backup metadata. No `manager` or `admin` role. |
| Home Assistant Core API | `homeassistant_api: true` | New in 2.2 so the app can GET entity state for ambient/context behaviour. |
| Host control | none | No reboot/shutdown or other host-control endpoints. |

Both network clients are deliberately **GET-only**:

- `supervisor_api.py` reads Supervisor status/backup/network information.
- `home_context.py` reads `http://supervisor/core/api/states`.

There are no service calls and no `POST`, `PUT`, `PATCH` or `DELETE` request paths in either client. Security regression tests assert these invariants.

## Fault contract

`faults.py` remains the existing pure, I/O-free fault engine. Version 2.2 does not change its thresholds or semantics. Priority remains:

1. **HIGH TEMP** — CPU temperature ≥ `cpu_temp_alert_c`.
2. **FAN STOPPED** — PWM is 0% while CPU temperature is ≥ `fan_min_temp_c` and fan hardware is present.
3. **NO BACKUP / OLD BACKUP** — missing or stale backup when HA status is available.
4. **LOW STORAGE** — free space on `/data` at/below the configured threshold.
5. **HA STATUS** — Supervisor status unavailable.
6. **UPDATES** — pending Supervisor/Core updates.

With urgent interruptions enabled (the default), these supersede contextual and normal display output. Character mode translates them into character states where possible; Current and Ambient use the standard full-screen alert renderer.

## Fan safety

The app **does not control the Raspberry Pi 5 fan**. `system_info.py` only reads the kernel `hwmon` state for RPM/PWM/status. The Raspberry Pi firmware/kernel fan controller remains authoritative, and no fan curve or GPIO code is written by this project.

## Key configuration

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

cpu_temp_alert_c: 80
fan_min_temp_c: 55
backup_max_age_hours: 48
storage_min_free_percent: 10
```

`mode` accepts `current`, `ambient`, or `character`. `ambient_scene` accepts `auto`, `landscape`, `stars`, `weather`, `waves`, `city`, `plant`, or `particles`.

## Architecture

```text
argon_oled.py       main loop and display-mode orchestration
system_info.py      local CPU/RAM/storage/fan/uptime metrics
supervisor_api.py   cached GET-only Supervisor status client
home_context.py     cached GET-only Home Assistant entity-state client
faults.py           pure urgent-fault evaluator
interruptions.py    urgent > contextual > normal arbitration
screens.py          original status/alert renderer
visual_modes.py     ambient art, contextual fact and character renderer
```

## Maintenance and testing

Run:

```bash
cd argon-one-v5-oled
python3 -m unittest discover -s tests -v
```

Before widening permissions, changing the fan path, adding GPIO, mapping host folders, or introducing any mutating API call, update the security model and `tests/test_config_safety.py`. The tests are intentionally designed to fail if those invariants regress.

## Rollback

The app has no persistent host-side state to migrate. To roll back, stop it and reinstall an earlier repository version/commit or restore a Home Assistant backup from before the upgrade. The same app slug is retained across releases.

## Attribution & License

This is a hardened modified distribution of the Home Assistant add-on originally developed by **Ben Wolstencroft**, itself based on the Argon ONE setup script from **Argon40**.

Upstream: <https://github.com/BenWolstencroft/home-assistant-addons/tree/main/argon-oled-addon>

MIT licensed. See `LICENSE`, `argon-one-v5-oled/LICENSE`, `THIRD_PARTY_NOTICES.md`, and the historical `argon-one-v5-oled/CHANGELOG.md`.
