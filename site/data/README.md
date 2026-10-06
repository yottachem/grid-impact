# Site data

Built by `analysis/exports.py` after every analysis run. Do not edit by hand.

| File | Contents | License |
|------|----------|---------|
| `sites_open.json` | Data center sites whose primary record is OSM, PNNL, or PeeringDB | ODbL-1.0 for OSM-derived records (© OpenStreetMap contributors); others CC-BY-4.0 |
| `sites_fractracker.json` | Sites whose primary record is FracTracker Alliance's Open U.S. Data Centers Tracker | **Non-commercial use only**, with attribution to FracTracker Alliance (their terms of service) |
| `counties.json`, `utility_exposure.json`, `utility_usage_bill.json` | Exposure and residential usage/bill by county and utility | CC-BY-4.0 (MW estimates include FracTracker-derived values; non-commercial reuse of those columns) |
| `capacity_household_cost.json`, `event_studies.json`, `case_studies.json` | Analysis results | CC-BY-4.0 |
| `meta.json` | Build time and per-source freshness | CC-BY-4.0 |

Keys in the site files are abbreviated: `x`/`y` lon/lat, `g` status group, `mw`/`lo`/`hi` estimated MW and range, `b` MW basis, `n` name, `o` operator, `c`/`s` county/state, `src` sources, `eta` expected online.
