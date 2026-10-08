"""Capacity auction cost per household, by utility and delivery year, for PJM, ISO New England, and MISO.

cost/household/yr = (auction total $ / market annual energy) x (zone price / market-wide price)
                    x household kWh/yr x residential peak factor

- Auction totals, zone prices, and data center attribution: reference/capacity_auctions.csv
  (PJM BRA reports; Monitoring Analytics; ISO-NE Forward Capacity Auction results, converted from
  $/kW-month to $/MW-day; MISO Planning Resource Auction results, seasonal since 2023/24 and stored as
  day-weighted annual figures with the four seasonal prices kept). Utility zones: reference/{pjm,isone,miso}_utility_zones.csv.
- Market annual energy: EIA-930 (calendar year the delivery year starts in, else latest).
- Household kWh/yr: utility's latest 12 months of EIA-861M residential sales / customers.
- Peak factor: capacity is charged on contribution to system peak, and homes peak harder
  than they consume on average. 1.0 (energy share) / 1.2 (central) / 1.4 (high).
- Applies directly to `default_service` utilities (restructured states, where default
  supply prices pass auction costs through). `regulated` utilities mostly recover the
  cost of their own plants; their figures show market exposure, not bill impact.
"""
import json

import pandas as pd

from transform.common import MARTS, ROOT, latest, write

PEAK_FACTORS = {"low": 1.0, "central": 1.2, "high": 1.4}
REF = ROOT / "reference"
MARKETS = {"PJM": ("PJM", "pjm_utility_zones.csv"), "ISONE": ("ISNE", "isone_utility_zones.csv"),
           "MISO": ("MISO", "miso_utility_zones.csv")}  # market: (EIA-930 code, zones)


def household_kwh() -> pd.DataFrame:
    m = pd.read_parquet(MARTS / "utility_month.parquet")
    m = m[m.res_customers > 0]
    last = m.groupby(["utility_id_eia", "state"]).period.transform("max")
    w = m[m.period > last - pd.DateOffset(months=12)]
    g = w.groupby(["utility_id_eia", "state"]).agg(mwh=("res_sales_mwh", "sum"), cust=("res_customers", "mean"),
                                                   months=("period", "nunique"), through=("period", "max"))
    g = g[g.months == 12]
    return (g.mwh * 1000 / g.cust).rename("kwh_per_home_yr").to_frame().join(g.through.rename("kwh_through")).reset_index()


def build() -> pd.DataFrame:
    homes = household_kwh()
    all_energy = pd.DataFrame(json.load(open(latest("eia930_annual", "annual_energy.json"))))
    frames = [build_market(m, code, z, homes, all_energy) for m, (code, z) in MARKETS.items()]
    return pd.concat(frames, ignore_index=True)


def build_market(market: str, code: str, zone_file: str, homes: pd.DataFrame, all_energy: pd.DataFrame) -> pd.DataFrame:
    auctions = pd.read_csv(REF / "capacity_auctions.csv")
    auctions = auctions[auctions.market == market]
    rto = auctions[auctions.lda == "RTO"].set_index("delivery_year")
    energy = all_energy[(all_energy.rto == code) & (all_energy.days >= 365)].set_index("year").energy_mwh
    zones = pd.read_csv(REF / zone_file)

    rows = []
    for dy, a in rto.iterrows():
        year = int(a.dy_start[:4])
        e_year = year if year in energy.index else int(energy.index.max())
        usd_per_mwh = a.total_cost_busd * 1e9 / energy[e_year]
        lda_prices = auctions[auctions.delivery_year == dy].set_index("lda").price_usd_mw_day
        dc_share = a.dc_attributable_busd / a.total_cost_busd if pd.notna(a.dc_attributable_busd) else None
        for z in zones.itertuples():
            chain = z.lda_chain.split(">")
            price = next((lda_prices[l] for l in chain if l in lda_prices), a.price_usd_mw_day)
            rows.append({"market": market, "utility_id_eia": z.utility_id_eia, "state": z.state, "zone": z.zone, "supply": z.supply,
                         "delivery_year": dy, "dy_start": a.dy_start, "zone_price_usd_mw_day": price,
                         "rto_price_usd_mw_day": a.price_usd_mw_day,
                         "usd_per_mwh_zone": usd_per_mwh * price / a.price_usd_mw_day,
                         "energy_year": e_year, "dc_share": dc_share,
                         "frr_not_exposed": market == "PJM" and z.utility_id_eia == 19876 and year < 2025})
    df = pd.DataFrame(rows).merge(homes, on=["utility_id_eia", "state"], how="left")
    df = df.merge(zones[["utility_id_eia", "state", "utility_name"]], on=["utility_id_eia", "state"])
    for k, f in PEAK_FACTORS.items():
        df[f"usd_per_home_yr_{k}"] = df.usd_per_mwh_zone * df.kwh_per_home_yr / 1000 * f
    df["usd_per_home_yr_dc_central"] = df.usd_per_home_yr_central * df.dc_share
    base = df[df.delivery_year == "2024/25"].set_index(["utility_id_eia", "state"]).usd_per_home_yr_central
    df["increase_vs_2024_25_central"] = df.usd_per_home_yr_central - df.set_index(["utility_id_eia", "state"]).index.map(base)
    return df.dropna(subset=["kwh_per_home_yr"])


def run() -> None:
    write(build(), MARTS, "capacity_household_cost")


if __name__ == "__main__":
    run()
