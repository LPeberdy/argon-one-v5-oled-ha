# Argon ONE OLED Display — Home Assistant Add-on Repository

A Home Assistant OS add-on that drives the 128x64 SSD1306 OLED on an
**Argon ONE V5 Industria** case (Raspberry Pi 5) with genuinely useful,
**exceptions-first** system status: it shows routine info (clock, HA
status, CPU, fan, RAM, storage, network, uptime, backup age) most of the
time, and automatically replaces that rotation with clear alert screens
when something needs attention.

This is a hardened, read-only fork of an existing community add-on. See
[Attribution](#attribution--license) below.

## Repository contents

```
.
├── repository.yaml            # Add-on store repository metadata
└── argon-one-v5-oled/         # The add-on itself
    ├── config.yaml            # Add-on manifest (permissions, options)
    ├── apparmor.txt           # Mandatory AppArmor confinement profile
    ├── Dockerfile / build.yaml
    ├── run.sh                 # s6 entrypoint
    ├── argon_oled.py          # Main loop: rotation + fault supersession
    ├── system_info.py         # Local system metrics (no network/API calls)
    ├── supervisor_api.py      # Read-only Supervisor API client (GET only)
    ├── faults.py              # Pure fault-priority engine (unit tested)
    ├── screens.py             # OLED rendering (routine + alert screens)
    ├── tests/                 # Unit tests (permissions, faults, screens, metrics)
    └── README.md / DOCS.md / CHANGELOG.md
```

## Install

1. In Home Assistant: **Settings → Add-ons → Add-on Store → ⋮ → Repositories**.
2. Add this repository's URL.
3. Install **Argon ONE OLED Display** from the store.
4. Ensure I2C is enabled on the host (see the add-on's own
   [README](argon-one-v5-oled/README.md#enabling-i2c-on-raspberry-pi)).
5. Start the add-on. `boot: auto` makes it start again after HAOS host
   restarts; see [Persistence](#persistence).

## Permissions

This add-on is built to the minimum privilege it needs to read local
metrics and display them — nothing else. Concretely, `config.yaml` and
`apparmor.txt` enforce:

| Capability | Setting | Why |
|---|---|---|
| I2C device | `/dev/i2c-1` only | The OLED is the only I2C peripheral this add-on drives; no bus scanning across `i2c-0..26`. |
| GPIO | `gpio: false` | The optional GPIO4 button is **omitted this release** — see [GPIO4 button](#gpio4-button-omitted-this-release). |
| Config volume | not mapped | No `map: config:rw` (or any other host folder). The add-on never reads or writes Home Assistant's `/config`. |
| AppArmor | `apparmor: true` | Enforced, not disabled — profile in `apparmor.txt` explicitly denies `/config`, `/ssl`, `/share`, `/backup` and only allows `/dev/i2c-1`, `/proc`/`/sys` metric files it reads, and its own `/data`. |
| Supervisor API | `hassio_api: true`, `hassio_role: backup` | Narrow status + backup role. The client has no POST method and only performs GET requests. No `homeassistant_api` (Core API) access. |
| Host control | none | No `host/reboot`, `host/shutdown`, or any other mutating endpoint is called. `supervisor_api.py`'s client **only issues `GET` requests** — there is no POST capability in the code at all. |
| Addon/manager role | none | The add-on never requests `manager` or `admin` roles, and never manages other add-ons. |

See [Status Contract](#status-contract) for exactly what read-only data
this add-on requests and how it behaves when that data isn't available.

The `backup` role is intentional and live-verified. Supervisor's role
middleware permits this role to read normal `*/info` endpoints and the
backup API, while excluding App management, host control, OS, store,
network mutation, and administrator endpoints. The token could authorize
backup mutations, so defense in depth is provided by `supervisor_api.py`:
its client implements GET only and exposes no generic method or POST path.
App update counts are deliberately omitted because listing Apps would
require the much broader `manager` role.

## Status Contract

Every screen and fault check is backed by a value that is either
genuinely known or explicitly reported as unavailable — the add-on never
fabricates a "0" or "OK" to paper over a failed read.

**Routine screens** (`screen_list`, rotates every `switch_duration`
seconds): `clock`, `hastatus` (HA status), `cpu` (usage + 1/5/15 load +
temp), `fan` (RPM + PWM), `ram`, `storage` (real host disk, see below),
`ip`, `uptime`, plus optional `logo`/`qr`.

**Storage is read from `/data`, not `/`.** The container's root
filesystem is an overlay of the image layers and does not reflect real
host free space; `/data` is always bind-mounted from the host's actual
data partition regardless of the `map` option, so it's the only path
that gives a non-misleading number. If `/data` can't be read, the
storage screen shows **"Unavailable"** — it never falls back to the
overlay figure.

**Home Assistant status is either `available` or it isn't.** If the
Supervisor API can't be reached, or the role lacks permission, the
`hastatus` screen shows **"Status: N/A"** rather than "0 updates" /
"Backup: OK" — those would be indistinguishable from a genuinely healthy
system otherwise.

**Faults supersede routine rotation.** Each cycle, `faults.py` evaluates
current metrics against configurable thresholds and returns an ordered
list of active faults. If any are active, the display shows only alert
screens (cycling every 5s) until they clear — no HA status, RAM, etc.
No user acknowledgement is required or possible; there is no ping-buttoning through routine screens while a fault is unresolved. Priority order (most urgent first):

1. **HIGH TEMP** — CPU temperature ≥ `cpu_temp_alert_c` (default 80°C).
2. **FAN STOPPED** — PWM duty is 0% while CPU is ≥ `fan_min_temp_c`
   (default 55°C, deliberately above the verified native curve's 50°C
   first threshold to avoid a transition false alarm) and a fan hwmon device was detected. If no fan hardware is
   detected at all, this is not raised (nothing to assert against).
3. **NO BACKUP** / **OLD BACKUP** — no backups exist, or the latest is
   older than `backup_max_age_hours` (default 48h). Only evaluated when
   HA status is available (see below — otherwise this can't be known).
4. **LOW STORAGE** — free space on `/data` ≤ `storage_min_free_percent`
   (default 10%). Only evaluated when storage was obtainable.
5. **HA STATUS** — Supervisor status API unreachable or role insufficient.
6. **UPDATES** — one or more pending Supervisor/Core updates. App update
   counts are omitted to avoid granting the `manager` role.

See `argon-one-v5-oled/tests/test_faults.py` for the exact, unit-tested
semantics of each condition, and `test_config_safety.py` for the
permission invariants above.

## Persistence

- `boot: auto` — the add-on starts automatically with Home Assistant.
- The manifest does not misuse Home Assistant's `watchdog` field: that
  field requires a TCP/HTTP health-check URL, and this display exposes no
  network service. Unexpected main-loop failures exit non-zero and are
  visible in the add-on logs.
- The main loop always clears the display in a `finally` block on exit so
  an add-on or host restart does not leave a stale/frozen screen.

## Maintenance

- Run the test suite before releasing: `cd argon-one-v5-oled && python3 -m unittest discover -s tests -v`.
  Some tests are skipped in a bare Python environment without `Pillow`,
  `luma.oled`, `qrcode`, and `requests` installed (the add-on's
  `requirements.txt`) — install those locally, or trust the in-container
  build, for full coverage.
- Bump `version` in `argon-one-v5-oled/config.yaml` and add an entry to
  `argon-one-v5-oled/CHANGELOG.md` for every release.
- Thresholds (`cpu_temp_alert_c`, `fan_min_temp_c`,
  `backup_max_age_hours`, `storage_min_free_percent`) and `screen_list`
  are user-configurable in the add-on's *Configuration* tab — no code
  change needed to tune them.
- Do **not** re-introduce `host/*` Supervisor calls, `map: config:rw`,
  `gpio: true`, or `hassio_role: manager`/`admin` without updating both
  this README and `tests/test_config_safety.py`, which will fail the
  build if privilege regresses.

## Rollback

This add-on has no persistent host-side state to migrate (no config
volume; its only writable area is its own `/data`, used solely for an
optional custom logo override):

1. In **Settings → Add-ons → Argon ONE OLED Display**, stop the add-on.
2. To roll back to a previous version, either reinstall from an earlier
   tag/commit of this repository (remove and re-add the repository
   pointed at the desired ref, or use the add-on store's version
   history if your Supervisor build retains it), or restore a Home
   Assistant backup taken before the upgrade.
3. Restart the add-on. No data migration or config cleanup is required
   in either direction.

## GPIO4 button (omitted this release)

Earlier iterations of this add-on used the case's GPIO4 button for
screen navigation and, more importantly, for **host reboot/shutdown**
via long-press. Both are removed here:

- Screen navigation via GPIO added a `gpio: true` grant and a background
  polling thread for a feature the exceptions-first design makes less
  necessary (the display now surfaces what matters without user input).
- Reboot/shutdown-via-button required the Supervisor `manager` role and
  POST access to `host/reboot` / `host/shutdown` — directly against the
  least-privilege goal of this hardening pass, and risky for an
  unauthenticated physical button (anyone with case access could
  reboot/shutdown the host).

**Assessment for a future release:** a *read-only* GPIO4 use (e.g.
short-press to force the next screen) could be reintroduced with
`gpio: true` alone, no Supervisor role change, and no power-control
code path — but it would need its own AppArmor device grant, a
debounced polling or edge-triggered implementation (the previous one had
several buggy iterations; see `CHANGELOG.md` history from `1.0.0`–`1.16.2`
in `argon-one-v5-oled/`), and unit tests for the input handling before
being considered safe to ship. Host power control via this add-on is not
recommended to be reintroduced at all — that responsibility belongs to
Home Assistant's own UI/automations, which already have the
appropriately elevated, audited access path.

## Attribution & License

This add-on is a hardened fork of the Home Assistant add-on originally
**developed by Ben Wolstencroft**, itself based on the Argon ONE setup
script from **Argon40**, and converted to a containerized, `bashio`-driven
Home Assistant add-on format. See `argon-one-v5-oled/CHANGELOG.md` for
the full version history, including the pre-fork `1.0.0`–`1.16.2` work
this release builds on.

Licensed under the MIT License — see `argon-one-v5-oled/LICENSE`.
