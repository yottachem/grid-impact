# PRD: Grid Impact Tracker

*Owner: Josh Ritchey. Status: v0.1, 2026-10-05.*

## Problem

US data center load is growing faster than at any point since the grid buildout. Regulators, utilities, and residents are arguing about who pays, but the public evidence is either:
- **maps** of where data centers are (FracTracker, Data Center Stress Index, Electric Choice), with no quantified effect on residents, or
- **one-off studies** (NRDC, IEEFA, EPRI, SemiAnalysis) that reach opposite conclusions and aren't kept current.

No public, regularly refreshed, method-transparent source connects **data center exposure** to **what residents pay and experience**.

## Users

| User | Need | Primary view |
|------|------|--------------|
| Resident / ratepayer | "Is my bill going up because of data centers?" | Utility lookup |
| Journalist / advocate | Defensible numbers with sources | National map, downloads, methods |
| PUC staff / analyst | Utility-level panel to compare against filings | Data downloads |
| (Later) Contributing resident | Add their own bill to fill local gaps | Bill submission |

## Goals (MVP, 6 weeks)

1. National utility-month panel of residential price, bill, and customers, refreshed automatically within 1 week of each EIA release.
2. A data center exposure index (MW or estimated MW per 1,000 residential customers) for every utility and county, built from at least 3 location sources with confidence labels.
3. Capacity cost translation ($/household/yr) for every RTO with a capacity market.
4. Three case studies (Dominion VA, ERCOT TX, Georgia Power) with a stated method and limitations.
5. A public static site with "data through" and "last checked" dates on every metric, plus downloadable marts.

**Non-goals (MVP):** real-time dashboards finer than daily, causal claims beyond the capacity-cost channel, crowdsourced data, water/land impacts.

## Success metrics

| Metric | Target |
|--------|--------|
| Source freshness | Every source within its `expected_max_gap_days`; stale feeds open an issue automatically |
| Coverage | ≥ 95% of residential customers (EIA-861) mapped to a utility-county exposure value |
| Data center reconciliation | Every record has status, MW basis, source list, confidence |
| Reproducibility | `uv run` from a clean clone rebuilds marts from raw snapshots |
| Credibility | Methods page cites every source and states counter-evidence (EPRI 2026) |

## Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| R1 | Each source is polled on its cadence and snapshotted only when the content changed; raw snapshots are immutable and dated | Must |
| R2 | New data triggers marts rebuild and site redeploy with no manual step (except curated sources) | Must |
| R3 | Every published metric shows its data period and last-checked date | Must |
| R4 | County is the join spine: utility↔county, data center→county, ACS/LEAD/EAGLE-I by county | Must |
| R5 | Data center records carry status, MW (reported/estimated), sources, confidence, first/last seen | Must |
| R6 | Weather, fuel, and inflation controls in the panel analysis | Must |
| R7 | Crowdsourced bills: publish only aggregates with n ≥ 10 per ZIP/utility-month; no PII retained | Later |
| R8 | Pending visibility: before an area reaches the threshold, anyone can see how many bill entries from that ZIP/utility-month are pending (e.g. "6 of 10 needed"); counts only, no values, until the threshold is met and the aggregate is published | Later |
| R9 | Data status: every page shows sources tracked, newest data, sources updated recently and added recently; a status page lists each source's added date, last check, last new data, and current/late state | Must (done 2026-10-07) |

## Key decisions

| Decision | Rationale |
|----------|-----------|
| DuckDB + Parquet, no server | Free, reproducible, laptop- and CI-scale |
| PUDL for annual history, EIA direct for monthly | PUDL stable lacks 861M monthly; EIA posts it ~2 months after the data month |
| GitHub Actions cron with change detection | Free on a public repo; freshness tied to upstream releases rather than a fixed calendar |
| Free and open data only | Redistribution rights matter for a public dataset |

## Risks

| Risk | Mitigation |
|------|------------|
| Data center MW mostly undisclosed | Square-footage estimates with ranges; label reported vs. estimated |
| Location sources incomplete (IM3/OSM ≈ 1,480 features vs. 3,300+ in public trackers) | Merge IM3, OSM, PeeringDB, FracTracker, utility filings; dedupe by distance + operator |
| Confounded price trends | Controls, peer-utility comparison, and the capacity channel as the causal anchor |
| Upstream URLs change (e.g. HIFLD Open shutdown 2025-08-26) | Freshness monitor; archived mirrors recorded in `sources.yaml` |
