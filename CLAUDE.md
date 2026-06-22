# Bambu Filament Tracker - Project Context

## What This Is

A HACS-compatible Home Assistant custom integration that persistently tracks per-tray filament consumption for Bambu Lab printers with AMS. Works alongside the existing Bambu Lab HACS integration (by greghesp).

**Repo**: https://github.com/tycop3land/bambu-filament-tracker
**Owner**: tycop3land (Tyler Copeland, tcopeland1994@gmail.com)

## Architecture

**Service-only integration** — no duplicate entities from the Bambu integration. Listens to state changes on Bambu Lab entities and maintains its own persistent storage.

Core components:
- `tracker.py` — State machine (IDLE → PRINT_STARTING → PRINTING → PRINT_COMPLETING → IDLE) with INTERRUPTED/RECOVERING states for crash recovery
- `store.py` — Persistent JSON via `helpers.storage.Store` in `.storage/bambu_filament_tracker.{entry_id}`
- `spool_registry.py` — Spool CRUD, auto-detection from tray attribute changes, matching by tag_uid or color+material
- `sensor.py` / `binary_sensor.py` — Entity platforms, updated via dispatcher signals (no polling)
- `config_flow.py` — 2-step: select Bambu printer → configure thresholds

Key design decision: The Bambu integration's `print_weight` sensor has a `weights` attribute with per-tray weight breakdown from the 3MF slicer metadata. This is the primary source for per-tray consumption. Fallback to tray `remaining` attribute deltas or single-tray assumption.

## Deployment

- Deployed via **HACS** (custom repository). Always commit and push after code changes.
- Card JS (`bambu-filament-tracker-card.js`) deployed via `shutil.copy2` to `www/` in `async_setup`
- User adds `/local/bambu-filament-tracker-card.js` as a Lovelace resource manually

## File Structure

```
custom_components/bambu_filament_tracker/
  __init__.py              - Setup, service registration, state listener bootstrap
  config_flow.py           - 2-step config flow
  const.py                 - Domain, storage keys, state machine phases
  models.py                - Spool, PrintRecord, TrackerState dataclasses
  store.py                 - SpoolStore: persistent JSON storage
  tracker.py               - ConsumptionTracker: state machine
  spool_registry.py        - SpoolRegistry: CRUD, matching, auto-detection
  sensor.py                - Sensor entities (remaining, %, color, material, totals)
  binary_sensor.py         - Binary sensors (low filament alerts)
  services.yaml            - Service definitions
  strings.json             - Config flow UI strings
  translations/en.json     - English translations
  manifest.json            - Integration metadata
  bambu-filament-tracker-card.js - Custom Lovelace card
```

## Bambu Integration Entities Consumed

- `sensor.{prefix}_print_status` — Print state (running, idle, finish, failed, prepare)
- `sensor.{prefix}_print_weight` — Total grams used; `weights` attr has per-tray breakdown
- `sensor.{prefix}_active_tray` / `active_tray_index` — Currently feeding tray
- `sensor.{prefix}_tray_1` through `tray_4` — Tray attrs: color, type, name, tag_uid, empty, remaining
- `binary_sensor.{prefix}_online` — Printer connected

## Git / Release Workflow

- Git author: `tycop3land <tcopeland1994@gmail.com>`
- Do NOT add `Co-Authored-By` trailers
- Manifest version must match the release tag
