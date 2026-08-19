# Argon ONE OLED Display Add-on for Home Assistant

Read-only system status on your Argon ONE Industria case's 128x64 OLED
screen (Raspberry Pi 5) — **exceptions-first**: routine info most of the
time, clear alert screens automatically when something needs attention.

> See the [repository README](../README.md) for the full permissions
> model, status contract, maintenance, and rollback procedure. This file
> covers installation and day-to-day configuration.

## Features

### Routine screens (rotate every `switch_duration` seconds)
- 🕐 **clock** — date and 7-segment time
- 🏠 **hastatus** — pending updates + backup age, or a clear "N/A" if the
  Supervisor API is unreachable
- 💻 **cpu** — usage %, 1/5/15 min load average, temperature
- 🌀 **fan** — RPM (if a tachometer is wired) and PWM duty cycle, read
  from the Raspberry Pi 5's native fan controller (kernel `hwmon`) —
  this add-on never writes to the fan curve, only reads it
- 🧠 **ram** — used/total and percentage
- 💾 **storage** — real host free space (see [Storage accuracy](#storage-accuracy))
- 🌐 **ip** — host network address
- ⏱️ **uptime** — days/hours/minutes since boot
- Optional, not in the default rotation: **logo**, **qr** (QR code to
  your Home Assistant URL)

### Alert screens (automatically supersede routine rotation)
When any of the following are true, the display shows only alert
screens (cycling every 5s) until resolved — see the [Status
Contract](../README.md#status-contract) for exact trigger conditions and
priority order:
- CPU temperature at/above threshold
- Fan not spinning while cooling is expected
- Backup missing or older than threshold
- Storage free space at/below threshold
- Home Assistant status unavailable (API unreachable or insufficient role)
- Updates pending

### Storage accuracy
Storage figures are read from the add-on's own `/data` directory, which
is always bind-mounted from the host's real data partition — **not**
from `/` (the container overlay), which would misleadingly show the
image layer instead of actual host free space. If `/data` can't be read
for any reason, the screen shows "Unavailable" rather than a
possibly-wrong number.

## Installation

1. Add this repository to your Home Assistant Add-on Store (see the
   [repository README](../README.md#install)).
2. Click **Install** on **Argon ONE OLED Display**.
3. Enable I2C on your Raspberry Pi if not already enabled (below).
4. Configure the add-on (see [Configuration](#configuration)).
5. Start the add-on. The manifest's `boot: auto` setting provides
   persistence across HAOS host restarts.

## Enabling I2C on Raspberry Pi

Before using this add-on, `/dev/i2c-1` must already exist on the HAOS
host. On the commissioned host this prerequisite is complete. The
one-time configurator used to add the supported boot parameters is not
a runtime dependency and can be removed after verification.

If the device is absent on another HAOS host, enable I2C using a
supported host method first. Do not disable add-on protection or grant
this display broad host access as a workaround. Only `/dev/i2c-1` is
exposed to this add-on (see [Permissions](../README.md#permissions)).

## Enabling the Raspberry Pi 5 native fan (required for the Fan screen and its alert)

**Important:** this add-on only *reads* the kernel's fan status; it does
not configure or modify the fan curve. On the commissioned Pi 5, the
native kernel policy has been verified as:

- below 50°C: off
- 50°C: 75/255 PWM (about 29%)
- 60°C: about 50%
- 67.5°C: about 70%
- 75°C: 100%
- 5°C hysteresis at each step

That supported native policy remains authoritative; no boot-file fan
overrides are required by this add-on. The default `fan_min_temp_c` is
55°C, above the first 50°C transition, so a momentary handover does not
produce a false **FAN STOPPED** alert. Change it only if the host's
independently configured native curve is intentionally different.

## Configuration

Example configuration:

```yaml
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
| `temp_unit` | `C` | `C` or `F` for displayed temperature |
| `switch_duration` | `30` | Seconds each routine screen is shown (5-300) |
| `screen_list` | `"clock hastatus cpu fan ram storage ip uptime"` | Space-separated routine screens, in order. Available: `logo`, `clock`, `cpu`, `ram`, `storage`, `temp`, `fan`, `uptime`, `ip`, `qr`, `hastatus` |
| `debug_logging` | `false` | Verbose logs for troubleshooting |
| `show_credits` | `true` | Show a brief attribution/version splash once at startup (no QR code) |
| `cpu_temp_alert_c` | `80` | CPU temp (°C) at/above which the HIGH TEMP alert fires |
| `fan_min_temp_c` | `55` | CPU temp (°C) above which the fan is expected to be spinning; default includes margin above the native 50°C first step |
| `backup_max_age_hours` | `48` | Backup age (hours) at/above which the OLD BACKUP alert fires |
| `storage_min_free_percent` | `10` | Free `/data` space (%) at/below which the LOW STORAGE alert fires |

## Hardware Requirements

- Argon ONE V5 Industria case with 128x64 SSD1306 OLED display
- Raspberry Pi 5 (64-bit/aarch64 only — see [why](#why-aarch64-only))
- I2C enabled on the Raspberry Pi (bus 1)

### Why aarch64 only?
Raspberry Pi 5 only runs Home Assistant OS as a 64-bit (aarch64) image,
and the native fan `hwmon` interface this add-on reads is a Pi 5-specific
kernel feature. There is no armhf/armv7 target for this hardware, so the
add-on is built for aarch64 only.

## Troubleshooting

### OLED screen not working
1. Check I2C is enabled: `ls /dev/i2c-1` should exist on the host.
2. Check the OLED is detected: `i2cdetect -y 1` should show a device at `0x3c`.
3. Check the add-on logs for errors.

### Fan alert firing when the fan seems fine
- Confirm your `/mnt/boot/config.txt` fan thresholds and this add-on's
  `fan_min_temp_c` agree.
- If your case has no tachometer wired, `rpm` will show "No Tach Signal"
  but PWM-based fault detection still works.

### "HA STATUS N/A" / hastatus shows unavailable
This means a read-only Supervisor API call failed. The App uses the narrow
`backup` role so it can show backup age plus normal system info without
receiving App-management or host-control access. See the
[permissions note](../README.md#permissions).

## Architecture

- **argon_oled.py** — main loop: routine rotation vs. fault-superseded
  alert rotation
- **system_info.py** — local system metrics only (CPU, memory,
  `/data` storage, fan `hwmon`, uptime, load) — no network calls
- **supervisor_api.py** — read-only (`GET`-only) Supervisor API client
- **faults.py** — pure fault-priority computation, fully unit tested
  independent of hardware/network
- **screens.py** — all OLED rendering, routine and alert
- **tests/** — permissions/config-safety, fault-priority, and rendering
  unit tests (hardware-independent, run without a Pi or OLED)

## Support

- GitHub Issues: see the [repository README](../README.md) for the repo URL.

## Credits

See the [repository README's Attribution & License](../README.md#attribution--license) section.

## License

MIT License - see [LICENSE](LICENSE).
