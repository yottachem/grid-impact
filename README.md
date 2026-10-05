# grid-impact

How is data center load growth affecting residential electricity customers? This project collects national grid, price, and reliability data on a schedule, overlays existing and proposed data centers, and quantifies resident-level impact (price, bill, energy burden, reliability). Results are published as a public site with open data.

Status: week 1 (scaffold + source verification). See `docs/PRD.md`.

## Run

```sh
uv sync
uv run python -m ingest.run --cadence all     # fetch every source, snapshot only changed data
uv run python -m ingest.freshness             # report stale sources
uv run pytest
```

Set `EIA_API_KEY` (free: https://www.eia.gov/opendata/register.php). Falls back to `DEMO_KEY` (rate-limited).

## Layout

| Path | Purpose |
|------|---------|
| `sources.yaml` | Source registry: URL, check cadence, freshness threshold, license |
| `ingest/` | One module per source; `common.snapshot()` writes dated raw files only when upstream changed |
| `transform/` | SQL models: raw → staged → marts (DuckDB) |
| `analysis/` | Notebooks |
| `site/` | Public front end |
| `data/` | `raw/` (immutable snapshots), `staged/`, `marts/`; not committed |

## License

Code: MIT. Derived data: CC-BY-4.0, subject to upstream licenses listed in `sources.yaml`, with two exceptions:

- **FracTracker** data center records are non-commercial only. They are used for analysis and the map with attribution, and published as a separate CC-BY-NC download, never mixed into the CC-BY marts.
- **OpenStreetMap**-derived records are ODbL-1.0 (© OpenStreetMap contributors).
