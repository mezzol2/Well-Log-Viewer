# OSDU Well Log Viewer

A desktop app for browsing and viewing well log curves — Gamma Ray, Bulk
Density, Neutron Porosity, Deep Resistivity, and more — in a standard
multi-track log display.

Wells are browsable in a **field → well → wellbore** tree; selecting a
wellbore renders its curves as linked, depth-aligned tracks. It reads
**real LAS files** (e.g. the openly licensed Volve dataset) or runs on
**synthetic data shaped like OSDU records** with zero setup.

## Features

- **Field → well → wellbore tree**, grouped by field.
- **Multi-track log display** — one curve per track, sharing a single
  depth axis (scroll or zoom one track and the rest follow), depth
  increasing downward, using standard conventions (NPHI reversed, RT
  logarithmic).
- **Curve picker** — choose exactly which curves to display; copes with
  files carrying many curves (the Volve LFP composite has 170).
- **Curve details** — description, provenance (including any mnemonic the
  app auto-renamed), sample coverage, depth range, and min/median/max.
- **Two data sources** behind one interface — synthetic mock data, or a
  folder of real LAS files.

## Quick start

```bash
pip install -r requirements.txt

# synthetic mock data (default, no setup):
python main.py

# real LAS files (e.g. downloaded Volve wells):
python main.py --las data/volve
```

Click any wellbore in the left-hand tree to load its curves.

Getting real data: Equinor's **Volve** dataset is openly licensed and
includes real wireline logs from the Norwegian North Sea. Download the
well-log LAS files into a folder and point `--las` at it (subfolders are
fine). See [DESIGN_NOTES.md](DESIGN_NOTES.md) for how the reader copes with
real-world LAS quirks.

## Architecture

The UI never touches a data source directly. Everything goes through the
`BaseClient` abstract interface (`client_interfaces/base.py`), whose methods
mirror real OSDU service calls:

| Method                     | Real OSDU equivalent                                  |
|----------------------------|-------------------------------------------------------|
| `search_wells()`           | Search Service — `POST /search/v2/query`, kind=Well   |
| `get_wellbores_for_well()` | Search Service, kind=Wellbore filtered by well id     |
| `get_well_log()`           | Wellbore DDMS (`/welllogs/{id}`) + Storage for curves |

Two implementations ship with the app:

- `client_interfaces/mock_client.py` — synthetic data, zero setup (default)
- `client_interfaces/las_client.py` — real well data from a folder of LAS files

**Connecting a real OSDU instance later** is an isolated change: add
`client_interfaces/real_client.py` implementing the same interface (handling
OAuth2 bearer tokens and the `data-partition-id` header), then switch one
line in `main.py`. The UI and data models don't change.

## Project structure

```
main.py                            entry point (--las flag selects data source)
models/osdu_models.py              Well, Wellbore, WellLog, LogCurve — shaped like OSDU schemas
mock_data/generator.py             synthetic dataset (layered facies -> realistic curve responses)
client_interfaces/base.py          BaseClient abstract interface
client_interfaces/mock_client.py   mock implementation
client_interfaces/las_client.py    real-data implementation over a folder of LAS files
ui/main_window.py                  main window: tree + curve picker + viewer
ui/curve_selector.py               curve picker and per-curve details panel
ui/log_viewer.py                   multi-track log display widget
```

## More

Design rationale, LAS-handling details, the mock dataset, and the roadmap
live in **[DESIGN_NOTES.md](DESIGN_NOTES.md)**.
