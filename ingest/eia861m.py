"""EIA-861M monthly utility-level sales, revenue, and customers, 2015 to current year.
EIA names the files differently by era; archived years rarely change, so the weekly
hash check only re-snapshots the current-year file in practice."""
from datetime import date

from ingest.common import http_get, snapshot

SOURCE_ID = "eia861m"
BASE = "https://www.eia.gov/electricity/data/eia861m/"
FIRST_YEAR = 2015


def file_for(year: int, current: int) -> str:
    if year == current:
        return f"xls/sales_ult_cust_{year}.xlsx"
    if year >= 2021:
        return f"archive/xls/sales_ult_cust_{year}.xlsx"
    if year >= 2017:
        return f"archive/xls/retail_sales_{year}.xlsx"
    return f"archive/xls/f826{year}.xls"


def run() -> bool:
    current = date.today().year
    changed = False
    for year in range(FIRST_YEAR, current + 1):
        path = file_for(year, current)
        content = http_get(BASE + path).content
        changed |= snapshot(SOURCE_ID, content, path.rsplit("/", 1)[1], {"year": year}) is not None
    return changed
