# Argon ONE OLED Display 2.2.0

## New display modes

- Added `mode: current|ambient|character` to the app configuration. `current` preserves the existing rotating status screens for backwards compatibility.
- Added **Ambient** mode: a living monochrome screensaver driven by Home Assistant state. `ambient_scene: auto` chooses among landscape, stars, weather, waves, city, plant, and particles; any scene can also be forced explicitly.
- Added **Character** mode: a small house creature that sleeps when the house is quiet at night, reacts to arrivals, rain, Pi heat, and faults, and uses expressions for urgent interruptions rather than the standard alert banner.

## Interruption hierarchy

All modes now share the same display priority:

1. **Urgent interruption** — existing `faults.py` faults, highest priority.
2. **Contextual interruption** — one relevance-ranked current fact shown briefly.
3. **Normal mode** — the selected current/ambient/character display.

`contextual_interruptions` and `urgent_interruptions` can be toggled independently. Contextual duration and minimum interval are configurable.

## Home Assistant context

- Added a GET-only Home Assistant Core state client using `http://supervisor/core/api/states`.
- Successful state snapshots are cached for 60 seconds by default (`ha_refresh_seconds` is configurable from 30–600 seconds); failed reads retry after 10 seconds.
- Context is derived generically from available weather, temperature, person, light, motion/occupancy/presence entities. Missing entity classes degrade gracefully.
- Recent `person.*` arrivals are retained briefly so ambient/character/context layers can react even though Home Assistant is intentionally polled slowly.

## Security / hardware

- `hassio_role` remains the narrow `backup` role; protection mode, I2C-only device access, GPIO policy, and native fan control are unchanged.
- The enforced AppArmor profile only adds read access to the three new bundled Python modules; no new host paths, devices, capabilities, or write access are granted.
- `homeassistant_api: true` is newly required so the app can read Home Assistant entity state through the official Core API proxy.
- The new Core client contains GET requests only. There are no service calls, POST/PUT/PATCH/DELETE requests, host-control endpoints, or GPIO writes.
- Existing Supervisor polling remains cached at 60 seconds for info and 5 minutes for backups.
