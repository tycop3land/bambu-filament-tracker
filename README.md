# Bambu Filament Tracker

A Home Assistant custom integration that persistently tracks filament consumption per AMS tray for Bambu Lab printers. Designed to work alongside the [Bambu Lab HACS integration](https://github.com/greghesp/ha-bambulab).

## Why?

The Bambu Lab HA integration resets usage sensors when the printer powers off, and doesn't break down per-tray consumption for multi-filament AMS prints. This integration solves both problems with persistent storage that survives power cycles and per-tray tracking using slicer weight data.

## Features

- **Persistent tracking** — Filament usage data survives printer power cycles and HA restarts
- **Per-tray breakdown** — Knows exactly how much each tray consumed in multi-filament prints
- **Auto-detection** — Detects spool changes when you configure filament via Bambu Handy
- **Spool registry** — Full history of every spool used, with per-print consumption records
- **Low filament alerts** — Binary sensors trigger when spools drop below a configurable threshold
- **Custom Lovelace card** — Visual dashboard with color swatches and progress bars
- **Crash recovery** — State machine persists mid-print, recovers from power loss or HA restarts

## Installation

### HACS

1. Add this repository as a custom repository in HACS
2. Install "Bambu Filament Tracker"
3. Restart Home Assistant
4. Go to Settings → Devices & Services → Add Integration → "Bambu Filament Tracker"
5. Select your Bambu Lab printer and configure thresholds

### Manual

1. Copy `custom_components/bambu_filament_tracker/` to your HA `custom_components/` directory
2. Restart Home Assistant
3. Add the integration via Settings → Devices & Services

### Lovelace Card

Add the card resource manually:

1. Go to Dashboard → Edit → Manage Resources
2. Add `/local/bambu-filament-tracker-card.js` as a JavaScript Module

Then add a card:

```yaml
type: custom:bambu-filament-tracker-card
entity_prefix: filament_tracker
show_empty_trays: true
show_totals: true
```

## Prerequisites

- [Bambu Lab HACS Integration](https://github.com/greghesp/ha-bambulab) installed and configured
- Bambu Lab printer with AMS connected

## Entities

### Per Tray (1-4)

| Entity | Description |
|--------|-------------|
| `sensor.filament_tracker_tray_N_remaining` | Remaining filament in grams |
| `sensor.filament_tracker_tray_N_remaining_pct` | Remaining filament percentage |
| `sensor.filament_tracker_tray_N_color` | Filament color hex code |
| `sensor.filament_tracker_tray_N_material` | Filament material type |
| `binary_sensor.filament_tracker_tray_N_low` | ON when below threshold |

### Global

| Entity | Description |
|--------|-------------|
| `sensor.filament_tracker_total_consumed` | Lifetime total consumption |
| `sensor.filament_tracker_last_print_usage` | Last print's consumption |

## Services

| Service | Description |
|---------|-------------|
| `bambu_filament_tracker.register_spool` | Manually register a new spool |
| `bambu_filament_tracker.load_spool` | Assign a spool to a tray |
| `bambu_filament_tracker.unload_spool` | Remove a spool from a tray |
| `bambu_filament_tracker.adjust_remaining` | Manually adjust remaining weight |
| `bambu_filament_tracker.sync_from_tray` | Force sync from Bambu tray data |

## How It Works

1. **Spool detection**: When you load a spool via Bambu Handy, the tray sensor attributes update in HA. This integration detects the change and either matches it to a known spool or creates a new one.

2. **Print tracking**: When a print starts, the tracker snapshots the current state. The Bambu integration's `print_weight` sensor includes a `weights` attribute with per-tray weight breakdown from the slicer. On print completion, these weights are deducted from each spool.

3. **Partial prints**: If a print is cancelled or fails, consumption is scaled proportionally by the print completion percentage.

4. **Crash recovery**: The tracker state is persisted every 60 seconds during printing. If HA or the printer restarts mid-print, the tracker recovers and finalizes consumption with the last known state.
