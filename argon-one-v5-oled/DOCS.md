# Argon ONE OLED Home Assistant Add-on — Developer Docs

See [README.md](README.md) for user-facing configuration and the [repository README](../README.md) for the security model.

## 2.2 architecture

The one-second OLED loop now has three layers:

1. collect local/Supervisor fault metrics and evaluate `faults.py`
2. read a cached Home Assistant context snapshot and rank contextual facts
3. ask `InterruptionController` whether to show urgent, contextual, or normal output

Normal output is selected by `mode`: `current`, `ambient`, or `character`.

## Project structure

```text
argon_oled.py          main loop and display-mode orchestration
system_info.py         local CPU/RAM/storage/fan/uptime/load metrics
supervisor_api.py      cached GET-only Supervisor API client
home_context.py        cached GET-only Home Assistant /states client
faults.py              pure urgent-fault evaluation
interruptions.py       contextual ranking + urgent/context/normal arbitration
screens.py             original routine and alert rendering
visual_modes.py        ambient, contextual and character rendering
run.sh                 bashio entry point
Dockerfile             container build
config.yaml            manifest, permissions and options
apparmor.txt           enforced confinement profile
tests/                 hardware-independent unit/regression tests
```

## Home Assistant context client

`home_context.py` reads:

```text
GET http://supervisor/core/api/states
Authorization: Bearer $SUPERVISOR_TOKEN
```

It deliberately exposes no generic request method and no service-call path. There are no POST/PUT/PATCH/DELETE requests.

Successful snapshots are cached for `ha_refresh_seconds` (default 60 seconds). A failed refresh becomes unavailable immediately after an expired snapshot and retries after 10 seconds; stale successful data is not served indefinitely.

The derived context is generic rather than tied to hard-coded entity IDs:

- first usable `weather.*` entity
- plausible indoor `sensor.*` entities with `device_class: temperature`
- `person.*` occupancy and arrival transitions
- count of lights on
- active motion/occupancy/presence binary sensors
- local hour / quiet state

Device/internal temperature sensors are filtered heuristically out of the indoor-temperature aggregate. Missing inputs degrade gracefully.

## Interruption arbitration

`interruptions.py` is stateful only for timing/cycling; contextual fact evaluation itself is pure.

Priority is:

```text
urgent fault > contextual fact > normal mode
```

Context facts are relevance-ranked. Current ordering begins with arrivals, precipitation, indoor temperature exceptions, warm Pi, occupancy, late-night lights and generic weather.

Urgent faults preserve the priority returned by `faults.py` and cycle every five seconds when multiple faults are active.

Contextual facts are shown for `contextual_duration` seconds, then normal output resumes until at least `contextual_interval` has elapsed. The default initial delay is 30 seconds so startup is not immediately interrupted by ordinary context.

## Ambient renderer

`visual_modes.py` uses Pillow/luma drawing primitives only; no image-generation or external service dependency is involved.

`ambient_scene: auto` selects:

- precipitation → `weather`
- night → `stars`
- occupied home with several lights → `city`
- warm environment → `waves`
- quiet home → `plant`
- active motion → `particles`
- otherwise → `landscape`

The render loop animates locally every second. HA state is not re-fetched for every frame.

## Character renderer

Character expressions are derived from the same context plus local CPU temperature and the current interruption:

- quiet night → sleeping
- activity/occupancy → happy
- recent arrival → excited
- precipitation → umbrella
- warm CPU/home → hot/sweating
- HA unavailable → confused
- other faults → annoyed

Character mode keeps the creature visible during interruptions, adding a compact label rather than using `screens.draw_alert()`.

## Existing fault and fan contract

`faults.py`, `system_info.py`, `supervisor_api.py`, and the native fan read path are intentionally independent of the new mode system.

The app never writes fan PWM or fan curves. `SystemInfo.get_fan_speed()` remains read-only against `/sys/class/hwmon`.

## Permissions

2.2 keeps:

```yaml
hassio_api: true
hassio_role: backup
gpio: false
apparmor: true
devices:
  - /dev/i2c-1
```

and adds:

```yaml
homeassistant_api: true
```

This is required for the official Home Assistant Core API proxy. The code-side defence remains GET-only.

AppArmor adds only `r` rules for `/home_context.py`, `/interruptions.py`, and `/visual_modes.py`. No host path, device, capability, or write permission is added.

## Running locally

```bash
docker build -t argon-oled-test .
```

For a non-container debug run:

```bash
export DISPLAY_MODE=ambient
export AMBIENT_SCENE=auto
export CONTEXTUAL_INTERRUPTS=true
export URGENT_INTERRUPTS=true
export CONTEXTUAL_DURATION=8
export CONTEXTUAL_INTERVAL=300
export HA_REFRESH_SECONDS=60
export TEMP_UNIT=C
export SWITCH_DURATION=30
export SCREEN_LIST="clock hastatus cpu fan ram storage ip uptime"
export DEBUG_LOGGING=true
export SHOW_CREDITS=true
export ADDON_VERSION=2.2.0
export SUPERVISOR_TOKEN=your_token_here
export CPU_TEMP_ALERT_C=80
export FAN_MIN_TEMP_C=55
export BACKUP_MAX_AGE_HOURS=48
export STORAGE_MIN_FREE_PERCENT=10
python3 argon_oled.py
```

Without a valid Supervisor token, both Supervisor-backed status and Home Assistant context degrade to unavailable rather than fabricating healthy values.

## Tests

```bash
python3 -m unittest discover -s tests -v
```

Key suites:

- `test_faults.py` — existing urgent-fault semantics
- `test_system_info.py` — local metrics/fan reads
- `test_supervisor_api.py` — Supervisor availability/caching/GET-only behaviour
- `test_screens.py` — original renderer
- `test_home_context.py` — HA state derivation, Celsius conversion, TTL/failure behaviour
- `test_interruptions.py` — relevance, priority, cycling and timing
- `test_config_safety.py` — manifest/AppArmor/API/GPIO least-privilege invariants

## Development workflow

1. Make code changes on a feature branch.
2. Run the complete unit suite and rendering smoke tests where Pillow/luma are available.
3. If permissions or API access change, update both the security docs and `test_config_safety.py`.
4. Keep HA/Supervisor polling decoupled from the one-second animation loop.
5. Never introduce fan writes, GPIO access, host control, broad host mounts, `manager`/`admin`, or mutating API methods without an explicit security redesign.
6. Bump `config.yaml` version and add release notes.
