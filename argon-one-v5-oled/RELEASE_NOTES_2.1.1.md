# Argon ONE OLED Display 2.1.1

## Fixed

- Decoupled the one-second OLED/local-system refresh loop from Home Assistant Supervisor API polling.
- Cached Supervisor/Core/network information for 60 seconds and backup information for 5 minutes.
- Shared the cached Supervisor endpoint snapshots between fault evaluation and screen rendering, preventing duplicate HTTP requests when the HA Status screen is active.
- Failed Supervisor refreshes now return unavailable once the previous successful value has expired, preserving `HA STATUS N/A` and fault behaviour instead of serving stale success indefinitely.
- Failed refreshes are retried after 10 seconds, faster than the normal successful-data TTL but without returning to one-request-per-second polling.

## Security / hardware

- No permissions, Supervisor role, AppArmor, device mappings, GPIO access, or host-control capabilities changed.
- Raspberry Pi 5 fan handling remains read-only through the existing local hwmon paths; the native firmware/kernel fan controller is untouched.
