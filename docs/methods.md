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

## Controls and measured load (`marts/utility_month`, week 3)

- **Measured load growth** (time-varying exposure): trailing-12-month commercial sales vs. the same months of 2019 (`com_growth_vs_2019`), plus commercial + industrial (`ci_growth_vs_2019`). Commercial-only is the cleaner data center signal; C+I also picks up oil field (e.g. Permian), crypto, and factory load. Top commercial growth through Jul 2026: Omaha PPD +143%, Indiana Michigan Power +94%, OG&E +61%, APS +53%, Dominion +41%.
- **Inflation:** BLS CPI-U all items for the utility's Census region, expressed in dollars of the latest CPI month. **BLS stopped publishing metro-area electricity CPI after December 2024** (API returns "No Data Available" for 2025+), so metro electricity indexes are history only; regional and national series continue.
- **Weather:** NOAA nClimDiv county heating and cooling degree days, averaged over each utility's EIA-861 service counties weighted by population. Contiguous US only (no AK, HI, DC).
- **Generation:** EIA-860M generator inventory (operating, planned, retired, canceled) by balancing authority; monthly snapshots are kept so slipped retirements can be tracked going forward.

## Capacity cost per household (`marts/capacity_household_cost`, week 4)

- Auction totals, zone prices, cleared MW: `reference/capacity_auctions.csv`, from PJM BRA reports (2024/25, 2025/26, 2028/29 reports; the 2028/29 report's Table 2 covers 2018/19-2028/29).
- Data center attribution: Monitoring Analytics (PJM's market monitor) — $9.3B of the 2025/26 auction (63% of that year's increase, as cited by IEEFA) and $23.1B across the 2025/26-2027/28 auctions (2025 State of the Market, 2026-03-12, via Utility Dive). The remaining $13.8B is split between 2026/27 and 2027/28 in proportion to auction cost. No attribution yet for 2028/29.
- cost per home per year = (auction total / PJM annual energy from EIA-930) × (zone price / RTO price) × household kWh/yr × residential peak factor (1.0 / 1.2 / 1.4). Capacity is charged on peak contribution, and homes peak harder than their energy share.
- Applies directly to `default_service` utilities (restructured IL, NJ, PA, OH, MD, DE, DC), where default supply passes auction prices through. `regulated` utilities mostly recover the cost of their own plants. Dominion self-supplied (FRR) through 2024/25. Zone assignments: `reference/pjm_utility_zones.csv`.
- The auction total is "cleared MW × price," which PJM notes is not the same as cost to load (self-supply and bilateral hedges are not exposed). The per-kWh figure is an upper-bound average for unhedged load.

**Result (restructured PJM utilities, central peak factor, median home ~10,350 kWh/yr):** capacity cost per home per year $46 in 2024/25, $217 (range $180-253) in 2025/26, $237 ($198-277) in 2026/27, $242 ($201-282) in 2027/28 and 2028/29. Increase vs 2024/25: about $190/yr (~$16/month). Portion attributed to data center load by the market monitor: about $137/yr (2025/26) and $100-103/yr (2026/27, 2027/28). By utility in 2026/27: $156 (PSE&G) to $305 (Potomac Edison MD), driven by kWh per home. Delmarva MD shows a decrease vs 2024/25 because its DPL-South zone cleared at $426.17 that year. Cross-check: $329.17/MW-day × 365 × 2.0-2.5 kW household peak contribution = $240-300/yr.

## Panel regressions (`analysis/panel.py`, week 4)

- Outcome: ln(inflation-adjusted residential price); utility-state and month fixed effects; heating and cooling degree days; SEs clustered by utility. 326 utility-states, 2015-01 to 2026-07.
- **Local load (within balancing authority × month):** elasticity of residential price to the utility's own commercial load -0.026 (95% CI -0.045 to -0.007). A 40% load rise implies about -0.9% relative to peers in the same market. Local load growth has not raised local residential prices relative to regional peers; if anything, more sales spread fixed costs.
- **PJM vs rest of US (ref. 2020):** no difference 2017-2021; +3.3% 2022, +11.1% 2023, +11.1% 2024, +12.7% 2025, +15.7% 2026. The premium **began in 2023, before the capacity price spike** (consistent with 2022 gas prices locked into restructured states' default-service procurements) and widened in 2025-2026 when capacity costs arrived.
- **Within PJM, restructured vs regulated (ref. 2020):** +18.3% in 2026, but pre-2020 coefficients are positive and declining (no clean parallel pre-trend), so this is weaker evidence.

## Case studies (`analysis/case_studies.py`, week 4)

Same-months comparison (Jan-Jul 2026 vs Jan-Jul 2025, inflation-adjusted): Dominion +17.0%, Texas statewide +2.6%, CPS Energy +1.9%, Georgia Power -1.9%. Full-year inflation-adjusted prices 2019-2025 fell or were flat in all three cases despite commercial load growth (Dominion +34%, Texas +22%, Georgia Power +7%). ERCOT has 88.4 GW of planned generation vs 26.7 GW in PJM (EIA-860M). Dominion's 2026 jump coincides with its first delivery year in the PJM auction and a base-rate increase of $11.24/month (SCC order 2025-11-25), which explains about a third of the 3.0¢/kWh nominal rise; fuel and rider changes are not yet decomposed.

## Known limitations

- Site-based exposure is a current snapshot; measured commercial load growth is the time-varying counterpart.
- Connecticut: Census uses planning regions, EIA uses legacy counties.
- Local exposure does not capture regional cost sharing (capacity markets). See the first descriptive result below.

## First descriptive result (2026-10-05, not causal)

Customer-weighted change in residential price, Aug 2020-Jul 2021 vs Aug 2025-Jul 2026: PJM +49.6% (46 utilities, 18.8M customers) vs rest of US +33.7% (348 utilities, 75.1M customers). Within PJM, utilities with no local data center exposure rose +47.1%. Outside PJM, high local exposure (+30.3%) is close to none (+26.7%). Points to regional pass-through via capacity markets; to be tested with controls in week 4.
