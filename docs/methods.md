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

The [Data status](status.html) page and every page footer show how many sources are tracked, which brought new data recently, when each was added, and whether any is late.


Seventeen automated sources are checked on the schedule above (the PJM and market monitor entries are entered by hand). Whenever any source brings new data, the full analysis reruns and the Findings page figures and wording are regenerated from it. When a check finds new data, the pipeline stores a dated copy, rebuilds the tables and analysis, and republishes the site in the same run. Each page footer shows the latest data month. A freshness monitor opens an issue when a source goes quiet longer than expected. Temporary upstream outages (timeouts, rate limits, server errors) are retried on the next run; real errors stop the run.

Some sources publish with a lag: monthly utility sales arrive about two months after the month ends, annual utility data about ten months after year end, and outage history once a year. Capacity auction results and market monitor findings are entered by hand when they are published.

## Data center sites

| Step | Rule | Why |
|------|------|-----|
| Status | FracTracker status grouped into operating (including expanding), approved or under construction, proposed (including pre-proposal), and cancelled (including suspended). Sites found only in other sources count as operating. | OpenStreetMap, PNNL, and PeeringDB list existing facilities |
| Merging | Sources in priority order FracTracker, OpenStreetMap, PNNL, PeeringDB. FracTracker projects are never merged with each other. Any other record within 500 m of an existing site joins it. | FracTracker entries are distinct curated projects; 500 m is campus scale |
| Floor vs. land area | PNNL campus polygons, and any floor area over 5 million sq ft, are treated as land area | PNNL campus area measures land; the largest real buildings are about 1-3 million sq ft |
| Power | Reported MW where available; otherwise floor area × 180 W per sq ft, or land area × 1.67 MW per acre, capped at 1,455 MW. Ranges use the 25th and 75th percentiles (102-298 W per sq ft; 0.86-2.96 MW per acre). Sites with no size data are counted but left out of MW totals. | Ratios fitted on 347 and 293 FracTracker sites that report both MW and size; the cap is the 95th percentile of reported site MW |

Result: 6,350 records merge into 2,792 sites.

**Quality checks** (every build; figures on the [Data status](status.html) page):

- *Duplicates.* Sources sometimes list one building twice (an owner LLC and an operator name, or a renamed listing). Nearby buildings of one operator are usually distinct (Stack NVA05 and NVA08), so pairs within 300 m with the same status are merged only when they share a building code (both "ATL1") or have nearly identical names and power within 25%. Pairs with different building codes (ATL01-1 and ATL01-3, Landbay A and B) are kept separate. Other nearby pairs with a shared operator or similar name are listed for review and kept, so some double counting can remain, most often a campus total listed next to its buildings. Reviewed pairs are recorded with their evidence in `reference/datacenter_pair_decisions.csv` and applied on every build; review starts with the pairs that carry the most MW.
- *Network facilities.* PeeringDB lists carrier interconnection points (for example Cogent or Lumen rooms in office buildings) alongside data centers. Unsized records from network carriers are typed as network facilities, hidden on the map by default, and left out of totals.
- *Benchmark.* Operating capacity is compared with Lawrence Berkeley National Laboratory's estimate of national data center electricity use (176 TWh in 2023); listed capacity at typical utilization exceeds it by 1.5-2x, consistent with capacity being planned build-out.
- *Corrections.* Anyone can report an error through the [correction form](https://github.com/yottachem/grid-impact/issues/new?template=data-correction.yml). Power is **planned capacity**, often a full build-out, not average load. The operating total (about 62 GW, range 46-107 GW) is above published estimates of actual US data center load (about 20-45 GW).

## Data center load by county and utility

- **County:** estimated MW by status per 1,000 households (ACS 2024 5-year).
- **Utility:** each site is placed in the retail service territories that contain it. Where territories overlap, those serving the site's state are preferred (territory boundaries are coarse at state lines), and the site's MW is split by each utility's customer density. Two corrections apply: "serving the state" uses the states EIA lists for the utility (the territory file records headquarters, so AEP Texas appears under Oklahoma), and where the territory file has no customer count (Texas wires utilities such as Oncor and CenterPoint) a company-reported count from `reference/territory_customers.csv` is used. Before this correction (2026-10-07), Texas data center load was mis-assigned to overlapping co-ops. Sites outside every territory (0.2% of MW) fall back to population-weighted shares of the utilities serving their county. EIA does not publish which utility serves a given site, so this is an approximation.
- **Denominator:** residential customers from each utility's most recent EIA-861 year within the last three. About 4% of operating MW sits at utilities with no residential count; it stays in totals, but those utilities have no per-customer figure.
- **Tiers:** operating plus pipeline MW per 1,000 residential customers: high 10 or more, medium 1-10, low under 1, none 0.

## Neighborhood costs (map)

The map shows household costs for all 50 states and DC: by county when zoomed out, and by census tract (about 4,000 people each; 84,119 tracts) when zoomed in. Tract data loads one state at a time as you zoom in.

- **Utility:** each tract is assigned the utility whose retail service territory contains the tract's representative point, using the same overlap rule as data center allocation.
- **Average annual bill:** that utility's residential revenue divided by customers for full-service customers (EIA-861, latest year). Customers who buy power from third-party suppliers are excluded, because the utility bills them only for delivery.
- **State-average fallback:** where the tract's utility has sold no power to homes in the last three years (most of Texas, where the wires utility only delivers, and about 2,900 other tracts nationwide), the state's average full residential bill is used and labeled "state average" (6,413 tracts, 3,511 of them in Texas).
- **Bill change:** inflation-adjusted (Census-region CPI), comparing the 2018-2019 average with the average of the latest two years. Two-year averages damp one-year swings such as co-op refunds and fuel true-ups.
- **Energy burden:** latest annual bill divided by the tract's median household income (ACS 2024 5-year). It is the only measure on the layer that varies within a utility, because income varies; bills are utility averages, so every tract a utility serves shares them. Nationally the middle 90% of tracts fall between 1.0% and 5.0% (median 2.2%).
- **Capacity cost per home:** shown for 2026/27 where default supply passes PJM auction prices through (Maryland and DC).
- **County layer:** household-weighted averages of its tracts' costs, plus estimated operating and pipeline data center MW per 1,000 households.

## Prices, controls, and measured load

- **Prices:** EIA-861M, 2015 to the latest month, excluding EIA's state adjustment and behind-the-meter rows. Residential price is revenue divided by sales; the average bill is revenue divided by customers. In restructured states, utility figures cover customers on default supply.
- **Inflation:** BLS CPI-U all items for the utility's Census region, in dollars of the latest CPI month. BLS stopped publishing metro-area electricity indexes after December 2024, so regional indexes are used.
- **Weather:** NOAA county heating and cooling degree days, averaged over each utility's service counties and weighted by population (contiguous US only).
- **Measured load growth:** trailing-12-month commercial sales compared with the same months of 2019. Data centers usually bill as commercial customers, so this tracks load that has actually arrived. Commercial plus industrial is also kept; it picks up oil field and factory load as well.

## Capacity cost per household (PJM)

*Figures and statements in this section update with each analysis run (last run {{run.date:date}}). See [Data status](status.html) for how they are checked.*

PJM, the grid operator for {{fact.pjm_states:int}} states and DC, buys generating capacity ahead of time in its Base Residual Auction. {{claim:m_capacity_prices}}

- **Cost per home per year** = (auction total ÷ PJM annual energy) × (zone price ÷ PJM-wide price) × household kWh per year × residential peak factor.
- **Peak factor:** capacity is charged on each customer's share of the system peak, and homes peak harder than their share of energy. The central estimate uses 1.2, with 1.0 and 1.4 as the range. A cross-check using a household peak contribution of 2.0-2.5 kW gives $240-300 a year at the capped price.
- **Data center share:** the market monitor found that data center load added ${{auc.dc_busd.y2025_26:f1}} billion to the 2025/26 auction and ${{auc.dc_busd_total:f1}} billion across the {{auc.dc_first_dy}} to {{auc.dc_last_dy}} auctions. The remainder after 2025/26 is split between the later years in proportion to auction cost. No attribution has been published for {{auc.no_dc_dy}}.
- **Who pays:** auction prices reach customers directly in restructured states (Illinois, New Jersey, Pennsylvania, Ohio, Maryland, Delaware, DC), where default supply passes them through. Regulated utilities mostly recover the cost of their own plants. Dominion supplied its own capacity outside the auction through 2024/25; AEP's regulated utilities still do.
- **Upper bound:** the auction total is cleared MW times price. PJM notes this overstates cost to customers, because some load is hedged or self-supplied.

{{claim:m_capacity_result}}

## Panel regressions

*Figures and statements in this section update with each analysis run (last run {{run.date:date}}). See [Data status](status.html) for how they are checked.*

The outcome is the log of inflation-adjusted residential price for {{local.n_units:int}} utility service areas, January 2015 to {{run.prices_through:month}}, with utility and month fixed effects, heating and cooling degree days, and standard errors clustered by utility.

- {{claim:m_local}}
- {{claim:m_pjm}}
- {{claim:m_pjm_restructured}}

## Reliability

*Figures and statements in this section update with each analysis run (last run {{run.date:date}}). See [Data status](status.html) for how they are checked.*

- **Utility test.** EIA-861 SAIDI (outage minutes per customer per year) and SAIFI (outages per customer), excluding major event days, {{rel.years}}, for {{rel.n_units:int}} utility-state units. The IEEE 1366 figure is used where reported, otherwise the utility's state-method figure ({{rel.share_state_method:f0}}% of utility-years, including Dominion); each utility and method gets its own fixed effect. Regressed on the log of the utility's commercial sales with balancing authority x year fixed effects. {{claim:m_rel_utility}}
- **County check.** ORNL EAGLE-I customer-hours without power per customer, 2018 onward. {{claim:m_rel_county}}
- **Limits.** These measure local distribution outages that have already happened. Bulk-supply risk is forward-looking: PJM's 2027/28 capacity auction cleared about {{fact.pjm_shortfall_2027_28_mw:r100}} MW below its reliability requirement.

## Case studies

*Figures and statements in this section update with each analysis run (last run {{run.date:date}}). See [Data status](status.html) for how they are checked.*

Inflation-adjusted residential price, {{run.latest_months}} {{case.ytd_year:year}} compared with the same months of {{case.last_full_year:year}}:

| Market | Change | Context |
|--------|--------|---------|
| Dominion Energy Virginia | {{case.dom.ytd:pct}} | {{claim:m_case_dominion}} |
| Baltimore Gas & Electric | {{case.bge.ytd:pct}} | {{claim:m_case_bge}} |
| Texas (statewide) | {{case.tx.ytd:pct}} | {{claim:m_case_texas}} |
| Georgia Power | {{case.ga.ytd:pct}} | {{claim:m_case_georgia}} |

## Resident bills

Residents can add the numbers from a recent electric bill through a Google Form (linked from the Your utility page). The form asks for ZIP code, utility, bill date, kWh, total amount, and optionally days billed, supplier, and electric heat. It does not collect names, emails, addresses, account numbers, or files, and does not require sign-in.

- Responses are stored in a private Google Sheet. A small public endpoint (Google Apps Script) returns only aggregates: the exact number of valid bills per ZIP code from the past 12 months, and, for ZIP codes with at least 10, the median monthly bill, median monthly kWh, and median price per kWh. Individual responses are never published.
- **Supply vs. delivery.** Optional questions split the bill into supply charges (the electricity itself: generation or energy charges, or a retail provider's charges), delivery charges (distribution, transmission, riders, and the fixed customer charge), the fixed customer charge on its own, and separately listed taxes and fees. A bill's split is used only if supply + delivery + taxes is within 8% of its total. Once a ZIP code has at least 10 bills with a usable split, the site shows median supply and delivery cost per kWh, the median fixed charge, and taxes and fees as a share of the bill. Data center growth can raise either part: supply through capacity and energy prices, delivery through new lines and substations.
- Bills are normalized to a 30-day month. A bill counts as valid if its date is within the past 12 months, normalized usage is 50-8,000 kWh, and the implied price is 5-80¢ per kWh.
- Pending counts are exact, so in a ZIP code with few homes a count of one or two can reveal that someone nearby submitted.
- Submissions are not verified; one person can submit more than once. Counts are labeled as pending until a ZIP code reaches the threshold, and medians limit the effect of outliers.

## How findings stay current

Each statement on the Findings page, and each result statement on this page, is stored in `analysis/claims.yaml` with the condition it rests on: for example, that a confidence interval lies entirely below zero, that one market's price rose more than another's, or that a figure is the highest on record. Figures fill in from each analysis run; facts entered by hand (rate orders, auction shortfalls, the number of PJM states) live in `reference/context_facts.csv` with their source and a review-by date.

- Every analysis run checks every condition. A statement whose condition no longer holds is replaced by its current figures without interpretation, marked "under review", and opened as a GitHub issue. Some statements have wording already reviewed for more than one outcome (for example, a local price effect that is negative, or indistinguishable from zero); the matching one is used.
- Each key figure also has a plausibility range. A figure outside it is treated as a possible data error rather than a new finding: the statements that use it are held for review, and the issue asks for the source data to be checked first.
- Rewritten wording is drafted with Claude and reviewed by the project owner before it is published; the change history is public in the repository.
- Hand-entered facts past their review date are listed on the [Data status](status.html) page and opened as an issue.

## Feedback

Every page links to a "Report an issue" form (Google Forms, no sign-in). It asks which page, what kind of issue, and what was seen, with an optional place and an optional email for a reply. Reports go to a private sheet and are never published; the pipeline only counts them so the owner is notified.

## Known limitations

- Site lists are incomplete, and most sites don't disclose power; estimates carry wide ranges.
- Site-based load is a current snapshot. Measured commercial load growth is the time-varying measure.
- Utility assignment of sites is approximate where territories overlap.
- Price differences have many causes. The regressions control for weather, inflation, and region, but the capacity-cost channel is the most direct causal link.
- Connecticut's counties differ between Census (planning regions) and EIA (legacy counties).
- Smaller utilities that report to EIA only annually are not in the monthly panel.

## Changelog

- **2026-10-08:** Findings and Methods wording generated from checked statements with conditions and plausibility ranges; hand-entered facts moved to a sourced reference table with review dates; "Report an issue" form added to every page.
- **2026-10-07:** Bill form adds optional supply, delivery, fixed charge, and taxes questions; published medians split supply vs. delivery.
- **2026-10-07:** Resident bill form launched with per-ZIP pending counts and medians at 10+ bills.
- **2026-10-07:** Reliability analysis added (utility SAIDI/SAIFI and county outages); outage minutes per customer added to the Your utility page.
- **2026-10-07:** Manual review of the 30 flagged pairs carrying the most MW: 14 duplicate or component records removed (about 6.9 GW, mostly proposed campuses listed twice), 16 pairs confirmed as separate.
- **2026-10-07:** Data center quality checks: duplicate merging (9 listings, 927 MW), network facilities typed and hidden by default, pairs pending review published, correction form added.
- **2026-10-07:** Household cost layer extended to all 50 states and DC (84,119 tracts). Data status page and footer added. Texas utility assignment corrected (see "Data center load by county and utility"), which moved about 4.6 GW of operating and 22.5 GW of pipeline data center load in Texas to Oncor.
- **2026-10-07:** Map replaced with a zoomable map (MapLibre, OpenFreeMap basemap) with clustered data center sites, a neighborhood cost layer for Virginia, Maryland, and DC, and a national county layer.
- **2026-10-06:** Public site launched.
- **2026-10-05:** First descriptive comparison (customer-weighted, no controls): residential prices rose 49.6% in PJM vs. 33.7% elsewhere between Aug 2020-Jul 2021 and Aug 2025-Jul 2026. Superseded by the panel regressions above.
- **2026-10-05:** AEP's regulated PJM utilities confirmed as self-supplying capacity (Utility Dive, 2026). Maryland case added.
