# Methods

This project measures how the growth of US data centers is affecting what residential electricity customers pay. It combines utility price and sales data, power market results, and data center locations, refreshes them automatically as sources publish, and publishes the results with the code that produces them.

## Approach

1. Build one list of existing and proposed data center sites from four sources, with each site's county, utility, and estimated power.
2. Measure each county's and utility's data center load relative to its households.
3. Assemble a monthly panel of residential price, bill, and usage for about 375 utilities from 2015 to the latest EIA release, with inflation, weather, and measured commercial load growth.
4. Test whether local data center load raises local residential prices, and measure regional effects through PJM's capacity market.
5. Compare four markets with different designs: Dominion (Virginia), Maryland (BGE and Pepco), Texas (ERCOT), and Georgia Power.

## Data sources

| Source | Used for | Checked | License |
|--------|----------|---------|---------|
| EIA-861M (monthly utility sales) | Residential price, bill, usage; commercial load growth | Weekly | Public domain |
| EIA-861 annual via PUDL (Catalyst Cooperative) | Residential customers, utility service counties | Weekly | CC-BY-4.0 |
| EIA-930 | Daily grid demand; annual energy by grid operator | Daily / monthly | Public domain |
| EIA-860M | Planned generation and retirements | Weekly | Public domain |
| PJM Base Residual Auction reports | Capacity prices, cleared MW, auction totals | Manual, per auction | Public |
| PJM Independent Market Monitor (Monitoring Analytics) | Share of capacity cost attributed to data center load | Manual | Public |
| BLS CPI-U | Inflation adjustment (Census-region all items) | Weekly | Public domain |
| NOAA nClimDiv | County heating and cooling degree days | Weekly | Public domain |
| Census ACS 5-year | Households and median income by county and tract | Monthly | Public domain |
| Census cartographic boundaries | County spine; tract boundaries for the neighborhood layer | Monthly | Public domain |
| HIFLD retail service territories (community mirror) | Utility territory polygons | Monthly | Public domain |
| ORNL EAGLE-I | County outage history, 2014-2025 | Monthly | CC-BY-4.0 |
| FracTracker Alliance, Open U.S. Data Centers Tracker | Existing and proposed sites, status, MW | Weekly | Non-commercial use, with attribution |
| PNNL IM3 Open Source Data Center Atlas | Existing sites and footprints | Weekly | Open (see repository) |
| OpenStreetMap via Overpass | Existing sites | Weekly | ODbL-1.0 |
| PeeringDB | Colocation facilities | Weekly | PeeringDB terms |

## How the site stays current

Each source is checked on the schedule above. When a check finds new data, the pipeline stores a dated copy, rebuilds the tables and analysis, and republishes the site in the same run. Each page footer shows the latest data month. A freshness monitor opens an issue when a source goes quiet longer than expected. Temporary upstream outages (timeouts, rate limits, server errors) are retried on the next run; real errors stop the run.

Some sources publish with a lag: monthly utility sales arrive about two months after the month ends, annual utility data about ten months after year end, and outage history once a year. Capacity auction results and market monitor findings are entered by hand when they are published.

## Data center sites

| Step | Rule | Why |
|------|------|-----|
| Status | FracTracker status grouped into operating (including expanding), approved or under construction, proposed (including pre-proposal), and cancelled (including suspended). Sites found only in other sources count as operating. | OpenStreetMap, PNNL, and PeeringDB list existing facilities |
| Merging | Sources in priority order FracTracker, OpenStreetMap, PNNL, PeeringDB. FracTracker projects are never merged with each other. Any other record within 500 m of an existing site joins it. | FracTracker entries are distinct curated projects; 500 m is campus scale |
| Floor vs. land area | PNNL campus polygons, and any floor area over 5 million sq ft, are treated as land area | PNNL campus area measures land; the largest real buildings are about 1-3 million sq ft |
| Power | Reported MW where available; otherwise floor area × 180 W per sq ft, or land area × 1.67 MW per acre, capped at 1,455 MW. Ranges use the 25th and 75th percentiles (102-298 W per sq ft; 0.86-2.96 MW per acre). Sites with no size data are counted but left out of MW totals. | Ratios fitted on 347 and 293 FracTracker sites that report both MW and size; the cap is the 95th percentile of reported site MW |

Result: 6,350 records merge into 2,792 sites. Power is **planned capacity**, often a full build-out, not average load. The operating total (about 62 GW, range 46-107 GW) is above published estimates of actual US data center load (about 20-45 GW).

## Data center load by county and utility

- **County:** estimated MW by status per 1,000 households (ACS 2024 5-year).
- **Utility:** each site is placed in the retail service territories that contain it. Where territories overlap, those based in the site's own state are preferred (territory boundaries are coarse at state lines), and the site's MW is split by each utility's customer density. Sites outside every territory (0.2% of MW) fall back to population-weighted shares of the utilities serving their county. EIA does not publish which utility serves a given site, so this is an approximation.
- **Denominator:** residential customers from each utility's most recent EIA-861 year within the last three. About 4% of operating MW sits at utilities with no residential count; it stays in totals, but those utilities have no per-customer figure.
- **Tiers:** operating plus pipeline MW per 1,000 residential customers: high 10 or more, medium 1-10, low under 1, none 0.

## Neighborhood costs (map)

The map's neighborhood layer covers census tracts (about 4,000 people each) in Virginia, Maryland, and DC; more states will be added.

- **Utility:** each tract is assigned the utility whose retail service territory contains the tract's representative point, using the same overlap rule as data center allocation.
- **Average annual bill:** that utility's residential revenue divided by customers for full-service customers (EIA-861, latest year). Customers who buy power from third-party suppliers are excluded, because the utility bills them only for delivery.
- **Bill change:** inflation-adjusted (Census-region CPI), comparing the 2018-2019 average with the average of the latest two years. Two-year averages damp one-year swings such as co-op refunds and fuel true-ups.
- **Energy burden:** latest annual bill divided by the tract's median household income (ACS 2024 5-year). It is the only measure on the layer that varies within a utility, because income varies; bills are utility averages, so every tract a utility serves shares them. Across the three states the middle 90% of tracts fall between 0.9% and 4.7% (median 2.1%).
- **Capacity cost per home:** shown for 2026/27 where default supply passes PJM auction prices through (Maryland and DC).
- **County layer (national):** estimated operating and pipeline data center MW per 1,000 households.

## Prices, controls, and measured load

- **Prices:** EIA-861M, 2015 to the latest month, excluding EIA's state adjustment and behind-the-meter rows. Residential price is revenue divided by sales; the average bill is revenue divided by customers. In restructured states, utility figures cover customers on default supply.
- **Inflation:** BLS CPI-U all items for the utility's Census region, in dollars of the latest CPI month. BLS stopped publishing metro-area electricity indexes after December 2024, so regional indexes are used.
- **Weather:** NOAA county heating and cooling degree days, averaged over each utility's service counties and weighted by population (contiguous US only).
- **Measured load growth:** trailing-12-month commercial sales compared with the same months of 2019. Data centers usually bill as commercial customers, so this tracks load that has actually arrived. Commercial plus industrial is also kept; it picks up oil field and factory load as well.

## Capacity cost per household (PJM)

PJM, the grid operator for 13 states and DC, buys generating capacity ahead of time in its Base Residual Auction. Prices rose from $28.92 per MW-day for 2024/25 to $269.92 for 2025/26, then reached the price cap in each of the next three auctions ($329.17, $333.44, $325.00). Without the cap, the 2028/29 auction would have cleared at $554.72.

- **Cost per home per year** = (auction total ÷ PJM annual energy) × (zone price ÷ PJM-wide price) × household kWh per year × residential peak factor.
- **Peak factor:** capacity is charged on each customer's share of the system peak, and homes peak harder than their share of energy. The central estimate uses 1.2, with 1.0 and 1.4 as the range. A cross-check using a household peak contribution of 2.0-2.5 kW gives $240-300 a year at the capped price.
- **Data center share:** the market monitor found that data center load added $9.3 billion to the 2025/26 auction and $23.1 billion across the 2025/26 to 2027/28 auctions. The remaining $13.8 billion is split between 2026/27 and 2027/28 in proportion to auction cost. No attribution has been published for 2028/29.
- **Who pays:** auction prices reach customers directly in restructured states (Illinois, New Jersey, Pennsylvania, Ohio, Maryland, Delaware, DC), where default supply passes them through. Regulated utilities mostly recover the cost of their own plants. Dominion supplied its own capacity outside the auction through 2024/25; AEP's regulated utilities still do.
- **Upper bound:** the auction total is cleared MW times price. PJM notes this overstates cost to customers, because some load is hedged or self-supplied.

**Result:** for a typical home in a restructured PJM state (about 10,350 kWh a year), capacity cost was $46 a year in 2024/25, $217 ($180-253) in 2025/26, $237 ($198-277) in 2026/27, and $242 ($201-282) in 2027/28 and 2028/29: about $190 a year more than 2024/25. The market monitor's findings attribute about $100-137 a year of it to data center load. The 2027/28 level is the highest in the series, about five times 2024/25 and 1.5 times 2018/19.

## Panel regressions

The outcome is the log of inflation-adjusted residential price for 326 utility service areas, January 2015 to July 2026, with utility and month fixed effects, heating and cooling degree days, and standard errors clustered by utility.

- **Local load:** comparing each utility only with others in the same regional grid in the same month, a 40% rise in its own commercial load goes with a **0.9% lower** residential price (95% CI 0.2% to 1.5% lower). Local load growth has not raised local residential prices relative to regional peers; more sales spread fixed costs.
- **PJM vs. the rest of the US** (2020 = 0): no difference from 2017 to 2021; +3.3% in 2022, +11.1% in 2023 and 2024, +12.7% in 2025, +15.7% in 2026. The gap opened **before** capacity prices spiked, consistent with 2022 natural gas prices being locked into default-supply contracts, and widened in 2025 and 2026 as capacity costs reached bills.
- **Within PJM, restructured vs. regulated:** +18.3% in 2026, but the two groups were not on parallel paths before 2020, so this comparison is weaker evidence.

## Case studies

Inflation-adjusted residential price, January to July 2026 compared with the same months of 2025:

| Market | Change | Context |
|--------|--------|---------|
| Dominion Energy Virginia | +17.0% | First year in the PJM capacity auction (its zone cleared at $444.26 for 2025/26). The state regulator approved a base-rate increase of $11.24 a month for a typical home in 2026, about a third of the rise; fuel and other charges are not yet separated. A new rate class for customers of 25 MW or more starts January 2027. |
| Baltimore Gas & Electric | +14.1% | Restructured; few large data centers locally. Real price rose 20% from 2019 to 2025 while local commercial load grew 4%. |
| Texas (statewide) | +2.6% | Energy-only market with 88 GW of planned generation (vs. 27 GW in PJM). Statewide totals include some areas outside ERCOT. |
| Georgia Power | -1.9% | Regulated, no capacity market; base rates frozen. |

## Known limitations

- Site lists are incomplete, and most sites don't disclose power; estimates carry wide ranges.
- Site-based load is a current snapshot. Measured commercial load growth is the time-varying measure.
- Utility assignment of sites is approximate where territories overlap.
- Price differences have many causes. The regressions control for weather, inflation, and region, but the capacity-cost channel is the most direct causal link.
- Connecticut's counties differ between Census (planning regions) and EIA (legacy counties).
- Smaller utilities that report to EIA only annually are not in the monthly panel.

## Changelog

- **2026-10-07:** Map replaced with a zoomable map (MapLibre, OpenFreeMap basemap) with clustered data center sites, a neighborhood cost layer for Virginia, Maryland, and DC, and a national county layer.
- **2026-10-06:** Public site launched.
- **2026-10-05:** First descriptive comparison (customer-weighted, no controls): residential prices rose 49.6% in PJM vs. 33.7% elsewhere between Aug 2020-Jul 2021 and Aug 2025-Jul 2026. Superseded by the panel regressions above.
- **2026-10-05:** AEP's regulated PJM utilities confirmed as self-supplying capacity (Utility Dive, 2026). Maryland case added.
