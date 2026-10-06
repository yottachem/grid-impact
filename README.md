# grid-impact

How is data center load growth affecting residential electricity customers? This project collects national grid, price, and reliability data on a schedule, overlays existing and proposed data centers, and quantifies resident-level impact (price, bill, energy burden, reliability). Results are published as a public site with open data.

**Site: https://yottachem.github.io/grid-impact/** (findings, data center map, your utility, methods). Rebuilt and republished automatically whenever a source publishes new data. See `docs/PRD.md` and `docs/methods.md`.

## Run

```sh
uv sync
uv run python -m ingest.run --cadence all     # fetch every source, snapshot only changed data
uv run python -m ingest.freshness             # report stale sources
uv run python -m transform.run                # build staged tables and marts
uv run python -m analysis.run                 # capacity cost, regressions, case studies, site data
uv run python site/build.py                   # build the site into site/dist
uv run pytest
```

Set `EIA_API_KEY` (free: https://www.eia.gov/opendata/register.php). Falls back to `DEMO_KEY` (rate-limited).

## Layout

| Path | Purpose |
|------|---------|
| `sources.yaml` | Source registry: URL, check cadence, freshness threshold, license |
| `ingest/` | One module per source; `common.snapshot()` writes dated raw files only when upstream changed |
| `transform/` | SQL models: raw → staged → marts (DuckDB) |
| `analysis/` | Capacity cost, panel regressions, case studies, site data exports |
| `reference/` | Hand-curated tables with citations (PJM auctions, utility zones) |
| `site/` | Public site: `templates/`, `data/` exports, `build.py` → `dist/` |
| `data/` | `raw/` (immutable snapshots), `staged/`, `marts/`; not committed |

## License

Code: MIT. Derived data: CC-BY-4.0, subject to upstream licenses listed in `sources.yaml`, with two exceptions:

- **FracTracker** data center records are non-commercial only. They are used for analysis and the map with attribution, and published as a separate CC-BY-NC download, never mixed into the CC-BY marts.
- **OpenStreetMap**-derived records are ODbL-1.0 (© OpenStreetMap contributors).
