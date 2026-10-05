# Plan: Grid Impact Tracker (data centers vs. residential energy burden)

## Step 0 (first action on approval)

Save this plan as `projects/grid-impact/inception-plan.md` in EA. Create `projects/grid-impact/README.md` (status, key dates, repo path, link to the inception plan). Append the scope decision to `decisions/log.md`. Then run the build in auto mode.

## Context

Josh wants to collect national energy data regularly, overlay existing and proposed data centers, and quantify how the added grid load affects local residents, then publish the results and later accept crowdsourced bill data.

Decisions made (2026-10-05):
- **Purpose:** portfolio / job-search piece. It should read as a well-run data product (PRD, sources, methods, shipped site), scoped to an MVP in about 6 weeks.
- **Scope:** national from day 1, built on monthly/annual utility- and county-level data, with 2 to 3 deep-dive case studies for depth.
- **Location:** a standalone git repo at `~/code/grid-impact` (outside iCloud). EA tracks it from `projects/grid-impact/README.md`.
- **Budget:** free and open data only, free-tier hosting.

**Prior art:** maps already exist: FracTracker Open US Data Centers Tracker (Apr 2026), Data Center Stress Index, Electric Choice tracker, Data Center Impact Dashboard. None of them gives a **resident-level quantified impact** (dollars per household, energy burden, reliability) linked to data center exposure with a stated method. That is the gap this project fills. Reuse their location data where licenses allow; don't build another map.

## Impact metrics (what "burden on residents" means)

| # | Metric | Unit | Primary source |
|---|--------|------|----------------|
| 1 | Residential price | ¢/kWh, monthly, by utility and state | EIA-861M (via PUDL) |
| 2 | Average residential bill | $/customer/month (revenue / customers) | EIA-861 / 861M |
| 3 | Energy burden | bill as % of median household income, county/tract | ACS + DOE LEAD tool |
| 4 | Capacity cost pass-through | $/household/yr from ISO capacity auctions | PJM BRA, MISO PRA, ISO-NE FCA, NYISO ICAP results |
| 5 | Metro electricity inflation | CPI electricity index vs. CPI all items | BLS CPI (metro series) |
| 6 | Reliability | SAIDI/SAIFI by utility; outage customer-hours by county | EIA-861 reliability; ORNL EAGLE-I |
| 7 | Load growth | BA hourly demand, annual peak, YoY | EIA-930 |
| 8 | Generation response | planned additions, delayed retirements, emissions | EIA-860M; EPA CAMPD |
| **X** | **Exposure (independent variable)** | data center MW (operating + pipeline) per 1,000 residential customers, by utility and county | Data center layer below |

Controls: weather (NOAA heating and cooling degree days), fuel (Henry Hub gas price), general inflation (CPI), utility type (IOU, co-op, muni) and market structure (RTO vs. vertically integrated).

## Data sources

### Energy and grid (all free)

| Source | Grain / cadence | Access | Notes |
|--------|-----------------|--------|-------|
| **PUDL** (Catalyst Cooperative) | Cleaned EIA-860/860M/861/923 and FERC Form 1 | Nightly Parquet/SQLite on AWS Open Data | Backbone. Avoids parsing raw EIA spreadsheets. |
| EIA API v2 | EIA-930 hourly BA demand; 861M monthly; electricity prices | Free API key | EIA-930 is the near-real-time feed |
| `gridstatus` (Python) | ISO load, LMP, queues for all 7 ISOs | Open source library | One interface for PJM/ERCOT/MISO/CAISO/NYISO/ISO-NE/SPP |
| ISO capacity auction reports | Annual, by zone | PDFs/CSVs, curated manually | PJM: $28.92 → $329.17/MW-day (2024/25 → 2026/27) |
| ERCOT Large Load Interconnection Status | Monthly | Public report | Direct data center pipeline signal for Texas |
| PJM Load Forecast Report | Annual, by zone | Public | Includes data center load adjustments by zone |
| BLS CPI | Monthly, metro | Free API | Electricity index by metro area |
| Census ACS 5-yr | Annual, county/tract | Free API | Income, households, heating fuel |
| DOE LEAD tool | Tract energy burden | Download | Low-income energy affordability baseline |
| ORNL EAGLE-I | 15-min outage counts by county | Figshare/ORNL download | Verify that 2025+ releases continue |
| EPA CAMPD | Hourly plant emissions | Free API | Fossil plant run-up near data center clusters |
| NOAA NCEI / CPC | Degree days | Free | Weather control |

### Data center locations (existing and proposed)

| Source | Coverage | Notes |
|--------|----------|-------|
| **PNNL IM3 Open Source Data Center Atlas** | Existing (from OSM, with footprint sq ft, county); projected sites to 2035 | Open, on GitHub (`IMMM-SFA/datacenter-atlas`). Starting layer. |
| OpenStreetMap via Overpass | Existing, refreshed weekly | Fresher than IM3 snapshots |
| FracTracker Open US Data Centers Tracker | Existing + proposed, with MW, status, community pushback | Best proposed-project source. Check license before redistributing. |
| PeeringDB facilities API | Colocation facilities with addresses | Free API |
| Utility IRPs and large-load filings (Dominion, Georgia Power, AEP, etc.) | Pipeline MW by utility | Manual curation for top ~10 utilities |
| County zoning/planning dockets | Proposed sites in hotspots | Manual, case studies only |

Every data center record carries: `status` (operating / construction / proposed / cancelled), `mw` plus `mw_basis` (reported / estimated from sq ft), `sources[]`, `confidence`, `first_seen`, `last_seen`. Weekly snapshots keep proposal histories (when a site appeared, grew, or was cancelled), which most trackers lose.

## Update timing (what the page shows, and when)

| Source | Publisher releases | We check | Freshness on page |
|--------|--------------------|----------|-------------------|
| EIA-930 hourly BA demand | Hourly (provisional, ~1 hr lag) | Daily, 06:00 ET; can move to hourly (free on a public repo) | ≤ 1 day |
| ISO load / LMP (`gridstatus`) | 5-min to hourly | Daily | ≤ 1 day |
| NOAA degree days | Daily | Daily | ≤ 1 day |
| EIA-861M monthly utility sales/revenue/customers | Monthly, data ~2 months behind | Weekly | Within 1 week of EIA release (data itself ~2 months old) |
| EIA-860M generator plans/retirements | Monthly, ~2 months behind | Weekly | Same as above |
| BLS CPI electricity (metro) | Monthly, mid-month for prior month (some metros bimonthly) | Weekly | Within 1 week of release |
| EPA CAMPD emissions | Quarterly | Weekly | Within 1 week of release |
| Data center layers (OSM, FracTracker, PeeringDB, IM3) | Continuous (OSM) to irregular | Weekly snapshot | ≤ 1 week; proposal history kept per snapshot |
| EIA-861 annual (reliability, service territory) | Early release ~mid-year, final ~fall, for prior year | Weekly | Within 1 week of release (data ~10 months old) |
| ORNL EAGLE-I outages | Historically annual bulk release | Monthly | Up to ~1 year old; verify current cadence in week 1 |
| ACS 5-yr, DOE LEAD | Annual (ACS in December), LEAD irregular | Monthly | Within 1 month of release |
| PUDL | Nightly builds; reflects EIA releases after processing | Used for history only | Recent months come straight from the EIA API so PUDL's lag doesn't hold back the page |
| Capacity auctions, utility IRPs, county dockets | Event-driven (PJM auction ~July) | Manual curation | Updated when curated; each event gets a backlog reminder |

**Exception, crowdsourced bills (Phase 4):** submissions are pooled daily, but a ZIP/utility-month cell appears on the page only after it reaches n ≥ 10 households. Below the threshold, the page shows "insufficient data" instead of a value.

## Geographic join spine

County is the common join unit:
- utility ↔ county: EIA-861 service territory table (PUDL). Polygons from the HIFLD retail service territory mirror (`hifld.publicenvirodata.org`; HIFLD Open was shut down 8/26/2025) or the Data Rescue Project archive.
- data center point → county FIPS (spatial join on Census TIGER).
- BA ↔ utility (EIA-861), ISO zone ↔ county (manual crosswalk, PJM first), metro CBSA ↔ county (Census delineation file).

## Storage and pipeline

- **Stack:** Python, DuckDB, Parquet. No server; the whole thing runs on a laptop and in GitHub Actions.
- **Layers:** `raw/` holds immutable fetches stamped with fetch date. `staged/` holds typed, cleaned tables. `marts/` holds analysis panels (`utility_month`, `county_year`, `datacenter_snapshot`).
- **Repo layout:** `ingest/<source>.py` (one module per source, shared fetch/snapshot helper), `transform/` (SQL models), `analysis/` (notebooks), `site/` (public front end), `docs/` (PRD, data dictionary, methods).
- **Schedules (GitHub Actions cron, free):** daily for EIA-930 and ISO load; weekly for OSM, FracTracker, and PeeringDB snapshots; monthly for EIA-861M, 860M, CPI, and EAGLE-I; annual for EIA-861, ACS, and LEAD; event-driven (manual) for capacity auctions and IRPs.
- **Release-driven refresh:** each scheduled job checks upstream for a new release (version, last-modified header, or new period in the API) and skips if nothing changed. Any new data triggers ingest → rebuild marts → rebuild and redeploy the site in the same workflow. The page therefore reflects new data within one check interval of the publisher releasing it. No manual step is needed except for manually curated sources.
- **Freshness on the page:** every chart and metric shows "data through <period>" and "last checked <date>". A freshness monitor opens a GitHub issue when a source goes quiet past its expected cadence (for example, 861M with no new month in 45 days), so a broken feed doesn't fail silently.
- **Data publishing:** marts attached to GitHub Releases, plus a Zenodo DOI once stable. Raw data stays out of git (`.gitignore`) and is rebuildable.

## Analysis approach

1. National panel: residential price and bill trends by utility (2015 to present), against data center exposure.
2. Exposure tiers (high / medium / none). Compare trends with weather, fuel, and inflation controls. Difference-in-differences around large load announcements where timing allows.
3. Capacity cost translation: auction price × zone obligation → $/household/yr. This is the cleanest causal channel, since PJM attributes 63% of the 2025/26 increase to data center load.
4. Case studies: Dominion/Loudoun-Prince William (VA), ERCOT/Abilene-DFW (TX), Georgia Power (GA).
5. **State the counter-evidence:** the June 2026 EPRI study finds data centers lowered average US rates over 2015 to 2024. Showing both sides is what makes the work credible.

## Public output

- Static site (Observable Framework with Python data loaders, on GitHub Pages; fall back to Evidence.dev if Framework maintenance looks stale). Pages: national map (exposure × price change), utility lookup ("your utility"), case studies, methods, downloads.
- `docs/PRD.md` and `docs/methods.md` serve as the portfolio artifacts: problem, users, metrics, source quality decisions, limitations.
- License: code MIT, derived data CC-BY-4.0, subject to each upstream license.

## Crowdsourcing (Phase 4, after MVP)

- Intake: Green Button "Download My Data" XML/CSV upload (standard format from many utilities) or a manual form (ZIP, utility, billing month, kWh, total $, rate plan).
- Privacy: no name, address, or account number. Drop the uploaded file after parsing. Publish only aggregates with n ≥ 10 per ZIP/utility-month. Get explicit consent and run a terms review before launch.
- Validation: implied ¢/kWh must fall within the utility's EIA range and tariff (OpenEI URDB). Flag outliers; rate-limit submissions.
- Value: monthly local bill data that EIA lacks at ZIP grain or with any timeliness.

## Milestones

| Week | Deliverable |
|------|-------------|
| 1 | Repo scaffold, PRD, source verification spike (API keys, licenses, current URLs; confirm the FracTracker and EAGLE-I terms) |
| 2 to 3 | Ingest PUDL, EIA-930, BLS, ACS, LEAD, IM3/OSM/FracTracker; county spine; first `utility_month` mart; scheduled Actions running |
| 4 to 5 | Exposure index, national panel analysis, capacity cost translation, 3 case studies |
| 6 | Public site, methods page, data release. Draft a LinkedIn post (Josh approves before posting). |
| Later | Crowdsourced bill intake; rate case curation; ISO-zone granularity |

## EA integration (on approval)

- Create `projects/grid-impact/README.md` with status, key dates, repo path, and a link to the PRD.
- Append to `decisions/log.md`: project scope (portfolio, national, free data, standalone repo).
- Add a note to `notes/backlog.md` under the right section for Phase 4 crowdsourcing and the rate case curation.
- Research notes on sources go to a vault. Confirm with Josh first (likely Prod Development).
- Tie into the job search: mention it in `projects/job-search/` talking points once the site ships.

## Verification

- Each ingest module runs idempotently, writes a dated raw snapshot, and passes row-count and schema checks (pytest + simple DuckDB assertions).
- Spot checks: Dominion residential ¢/kWh in the mart matches the EIA Electric Power Monthly table. PJM 2026/27 capacity price = $329.17/MW-day. Loudoun County shows the highest exposure.
- Scheduled GitHub Actions runs succeed for one full week before the site goes public.
- Methods page lists every source, its fetch date, its license, and its known gaps.

## Risks

- Data center MW is often undisclosed, so square-footage estimates carry wide error. Show confidence bands and label estimated values.
- Attribution: price changes have many causes. Present correlation with controls, use the capacity channel as the causal anchor, and avoid overclaiming.
- EIA-861 annual data lags about 10 months; 861M covers a sample of utilities. Note the coverage on the site.
- National scope can dilute depth. The case studies carry the narrative.
