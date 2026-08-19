# Argon ONE OLED Home Assistant Add-on — Developer Docs

This is a Home Assistant add-on for the Argon ONE case OLED display. See
[README.md](README.md) for user-facing docs and the [repository
README](../README.md) for the permissions model and status contract.

## Development

### Building locally

```bash
docker build -t argon-oled-test .
```

### Running locally

```bash
docker run --rm -it \
  --device /dev/i2c-1 \
  -e TEMP_UNIT=C \
  -e SWITCH_DURATION=30 \
  -e SCREEN_LIST="clock cpu ram" \
  argon-oled-test
```

### Debugging without a container

```bash
export TEMP_UNIT=C
export SWITCH_DURATION=30
export SCREEN_LIST="clock hastatus cpu fan ram storage ip uptime"
export DEBUG_LOGGING=true
export SHOW_CREDITS=true
export ADDON_VERSION=2.0.0
export SUPERVISOR_TOKEN=your_token_here   # optional: enables hastatus/ip/qr data
export CPU_TEMP_ALERT_C=80
export FAN_MIN_TEMP_C=55
export BACKUP_MAX_AGE_HOURS=48
export STORAGE_MIN_FREE_PERCENT=10
python3 argon_oled.py
```

Without `SUPERVISOR_TOKEN`, Supervisor-backed screens (`hastatus`, `ip`,
`qr`) degrade gracefully: `hastatus` shows "N/A" and triggers the
`ha_unavailable` fault, `ip` falls back to a local socket lookup.

### Unit testing (no hardware required)

```bash
# All tests
python3 -m unittest discover -s tests -v

# A single module
python3 -m unittest tests.test_faults -v
```

Tests that require `Pillow`/`luma.oled`/`qrcode`/`requests`
(`test_screens.py`, `test_supervisor_api.py`) skip gracefully if those
packages aren't installed in your environment — install
`requirements.txt` for full coverage. `test_faults.py`,
`test_system_info.py`, and `test_config_safety.py` have no such
dependency and always run.

## Project Structure

```
.
├── argon_oled.py          # Main loop: routine rotation + fault supersession
├── system_info.py         # Local system metrics (CPU, RAM, /data storage, fan, uptime, load)
├── supervisor_api.py      # Read-only (GET-only) Supervisor API client
├── faults.py              # Pure fault-priority evaluation engine
├── screens.py             # OLED rendering (routine + alert screens)
├── run.sh                 # s6/bashio entry point
├── Dockerfile             # Container build
├── config.yaml            # Add-on manifest: permissions + options
├── build.yaml             # Multi-arch build config (aarch64 only)
├── apparmor.txt           # Mandatory AppArmor confinement profile
├── README.md              # User documentation
├── CHANGELOG.md           # Version history
├── DOCS.md                # This file
├── LICENSE                # License information
└── tests/                 # Unit test suite
    ├── test_faults.py           # Fault priority + trigger-condition tests
    ├── test_system_info.py      # Metric collection tests
    ├── test_supervisor_api.py   # Read-only API client tests
    ├── test_screens.py          # Rendering tests
    ├── test_config_safety.py    # Permissions/least-privilege invariant tests
    └── run_tests.sh
```

## Module responsibilities

- **argon_oled.py** — owns the main loop only: decides routine vs. alert
  rotation each second by calling `faults.evaluate_faults()`, and
  dispatches to `screens.py`. Contains no metric-computation or
  privileged-API logic itself.
- **system_info.py** — local system metrics only (`/proc`, `/sys`,
  `os.statvfs`). No network calls, no Supervisor API. `get_disk_usage()`
  deliberately reads `/data`, not `/`, and reports `available=False`
  rather than falling back to the misleading container-overlay figure —
  see its docstring.
- **supervisor_api.py** — the *only* module that talks to the Supervisor
  API, and it is `GET`-only. There is no method to issue a POST, reboot,
  shut down, or manage add-ons. Every getter that depends on Supervisor
  data reports an explicit `available` flag so callers can distinguish
  "genuinely zero" from "couldn't ask."
- **faults.py** — pure functions, no I/O. Takes a metrics dict and
  threshold overrides, returns a priority-ordered fault list. This is
  what makes the exceptions-first behavior exhaustively unit-testable
  without a real Pi, display, or Supervisor.
- **screens.py** — all rendering. `draw_alert()` is the single alert
  renderer used for every fault type; routine screens degrade to
  "Unavailable"/"N/A" text rather than fabricating values when their
  underlying data source reports unavailable.

## Development Workflow

1. Make code changes.
2. Run unit tests: `python3 -m unittest discover -s tests -v`.
3. If you touch permissions (`config.yaml`, `apparmor.txt`, or any
   Supervisor/GPIO code path), confirm `test_config_safety.py` still
   passes — it encodes the least-privilege invariants this add-on
   commits to.
4. Test locally with Docker (optional, requires real I2C hardware for a
   full run).
5. Update `CHANGELOG.md` and bump `version` in `config.yaml`.
6. Commit and push changes.

## Contributing

1. Fork the repository.
2. Create a feature branch.
3. Add/update unit tests for your changes — especially anything touching
   `faults.py` thresholds/priority or `config.yaml`/`apparmor.txt`
   permissions.
4. Ensure all tests pass.
5. Update documentation (`README.md`, `CHANGELOG.md`, and the repository
   root `README.md` if the permissions/status contract changes).
6. Submit a Pull Request.

### Code Style

- Follow PEP 8 guidelines.
- Use descriptive variable names.
- Keep functions focused and modular; prefer adding a pure function to
  `faults.py` over embedding threshold logic in `argon_oled.py` or
  `screens.py`.
- Write unit tests for new features, particularly new fault conditions
  or new Supervisor API calls (which must remain `GET`-only).
