"""Stage EIA-861M: one row per utility x state x month with residential, commercial,
industrial, and total revenue, sales, and customers. All 2015+ files share one layout:
three header rows, then Year, Month, Utility Number, Name, State, Ownership, Data Status,
followed by (revenue k$, sales MWh, customers) for five sectors."""
import glob

import pandas as pd

from transform.common import RAW, STAGED, write

SECTORS = ["res", "com", "ind", "trans", "total"]
COLS = ["year", "month", "utility_id_eia", "utility_name", "state", "ownership", "data_status"] + [
    f"{s}_{m}" for s in SECTORS for m in ("revenue_kusd", "sales_mwh", "customers")
]


def _files() -> list[str]:
    """Newest snapshot of each yearly file."""
    by_name = {}
    for f in sorted(glob.glob(str(RAW / "eia861m" / "*" / "*.xls*"))):
        by_name[f.rsplit("/", 1)[1]] = f
    return sorted(by_name.values())


def build() -> pd.DataFrame:
    frames = []
    for f in _files():
        df = pd.read_excel(f, header=None, skiprows=3, names=COLS)
        frames.append(df[df["year"].apply(lambda v: str(v).strip().isdigit())])
    df = pd.concat(frames, ignore_index=True)
    for c in COLS[7:] + ["year", "month", "utility_id_eia"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["year"], df["month"] = df["year"].astype(int), df["month"].astype(int)
    df["period"] = pd.to_datetime(dict(year=df.year, month=df.month, day=1))
    # EIA's imputed estimates for small utilities and behind-the-meter solar are not utilities
    df["is_adjustment"] = df["utility_name"].str.contains("Adjustment", case=False, na=False) | df["utility_id_eia"].isin([0, 88888, 99999])
    df["is_btm"] = df["ownership"].eq("Behind the Meter")
    # Residential metrics (cents/kWh = k$ * 100 / MWh)
    sold = df["res_sales_mwh"] > 0
    cust = df["res_customers"] > 0
    df.loc[sold, "res_price_cents_kwh"] = df.loc[sold, "res_revenue_kusd"] * 100 / df.loc[sold, "res_sales_mwh"]
    df.loc[cust, "res_bill_usd"] = df.loc[cust, "res_revenue_kusd"] * 1000 / df.loc[cust, "res_customers"]
    df.loc[cust, "res_kwh_per_customer"] = df.loc[cust, "res_sales_mwh"] * 1000 / df.loc[cust, "res_customers"]
    df = df.drop_duplicates(["utility_id_eia", "state", "period", "ownership"], keep="last")
    return df.sort_values(["state", "utility_id_eia", "period"]).reset_index(drop=True)


def run() -> None:
    write(build(), STAGED, "eia861m_utility_month")


if __name__ == "__main__":
    run()
