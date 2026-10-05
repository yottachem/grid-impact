# Methods (working draft)

*Records each modeling decision when it's made. The public methods page is built from this file in week 6.*

## Data center sites (`marts/datacenter_sites`)

| Step | Rule | Why |
|------|------|-----|
| Sources | FracTracker, OpenStreetMap, PNNL IM3 atlas, PeeringDB | No single source is complete; only FracTracker has status and MW |
| Status | FracTracker status grouped into operating (incl. expanding), construction (approved/permitted/under construction), proposed (incl. pre-proposal), cancelled (incl. suspended). Records found only in other sources count as operating. | OSM/PNNL/PeeringDB list existing facilities |
| Merge | Priority order FracTracker > OSM > PNNL > PeeringDB. FracTracker records are never merged with each other. Any other record within 500 m of an existing site joins it. | FracTracker entries are curated, distinct projects; 500 m is campus scale |
| Floor vs. land area | PNNL campus polygons and any "floor area" over 5M sq ft are treated as land area | PNNL campus area is land; the largest real buildings are ~1-3M sq ft |
| MW estimate | Reported MW; else floor area × median W/sq ft; else land area × median MW/acre, capped at the 95th percentile of reported site MW (1,455 MW). Ranges use the 25th/75th percentiles. Else unknown (counted, excluded from MW totals). | Ratios fitted on FracTracker sites reporting both MW and size: 180 W/sq ft (IQR 102-298, n=347); 1.67 MW/acre (IQR 0.86-2.96, n=293) |

Reported and estimated MW is **capacity** (often full planned build-out), not average load. The operating total (~62 GW, range 46-107) is above estimates of actual US data center load (~20-45 GW).

## Exposure (`marts/county_exposure`, `marts/utility_exposure`)

- **County:** MW by status per 1,000 households (ACS 2024 5-year). ORNL EAGLE-I modeled electricity customers are kept as a secondary denominator; they are missing ~65 counties.
- **Utility:** each site is placed in the HIFLD retail service territories that contain it. Where several overlap, territories based in the site's own state are preferred (polygons are coarse at state lines), and MW is split by customer density (customers / area). Sites outside every polygon (0.2% of MW) fall back to population-weighted county shares of EIA-861 service territories.
- **Denominator:** residential customers (bundled + delivery) from each utility's latest EIA-861 year within the last three years. 4% of operating MW sits at utilities with no residential count; it stays in totals, but those utilities get no per-customer ratio.
- **Exposure tier:** operating + pipeline MW per 1,000 residential customers: high ≥ 10, medium 1-10, low > 0-1, none = 0.

## Prices (`marts/utility_month`)

- EIA-861M 2015-present, excluding EIA's state adjustment rows and behind-the-meter rows.
- Residential price = revenue / sales; average bill = revenue / customers.
- 861M covers ~375 larger utilities. Utility-level prices in restructured states reflect full-service customers only.

## Known limitations

- Exposure is a current snapshot; it does not yet vary over time with site online dates.
- Connecticut: Census uses planning regions, EIA uses legacy counties.
- Local exposure does not capture regional cost sharing (capacity markets). See the first descriptive result below.

## First descriptive result (2026-10-05, not causal)

Customer-weighted change in residential price, Aug 2020-Jul 2021 vs Aug 2025-Jul 2026: PJM +49.6% (46 utilities, 18.8M customers) vs rest of US +33.7% (348 utilities, 75.1M customers). Within PJM, utilities with no local data center exposure rose +47.1%. Outside PJM, high local exposure (+30.3%) is close to none (+26.7%). Points to regional pass-through via capacity markets; to be tested with controls in week 4.
