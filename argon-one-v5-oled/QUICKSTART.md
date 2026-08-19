# Quick start

## Host prerequisite

The OLED requires I2C bus 1. On the commissioned Home Assistant OS host,
I2C has already been enabled and `/dev/i2c-1` is present; the configurator
used for that one-time boot change is **not** a runtime dependency.

If `/dev/i2c-1` is absent on another host, stop here and enable I2C using a
supported HAOS method before installing this add-on. Do not disable
protection mode or run an arbitrary installer merely to make the display
container privileged.

## Install

1. In Home Assistant, open **Settings → Add-ons → Add-on Store → ⋮ → Repositories**.
2. Add this repository's public GitHub URL.
3. Install **Argon ONE OLED Display**.
4. Keep the default configuration initially:

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

5. Start the add-on. `boot: auto` starts it after future HAOS host reboots.
6. Confirm the log reports successful OLED initialization and visually
   confirm the normal screen rotation.

## Verify

- OLED: useful pages rotate and alert pages supersede them when a tested
  threshold is crossed.
- Fan: the add-on reports RPM/PWM but never changes the native Pi 5 curve.
- Permissions: only `/dev/i2c-1`, AppArmor, `gpio: false`, and the read-only
  Supervisor client are used.
- Restarts: restart the add-on, then perform a planned HAOS host restart and
  confirm the display returns automatically.

See [README.md](README.md) for the status contract, native fan policy,
maintenance, and rollback.
