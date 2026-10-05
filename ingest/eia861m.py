"""EIA-861M monthly utility-level sales, revenue, and customers (current-year file)."""
from datetime import date

from ingest.common import http_get, snapshot

SOURCE_ID = "eia861m"
BASE = "https://www.eia.gov/electricity/data/eia861m/"


def run() -> bool:
    year = date.today().year
    fname = f"sales_ult_cust_{year}.xlsx"
    content = http_get(BASE + "xls/" + fname).content
    return snapshot(SOURCE_ID, content, fname, {"year": year}) is not None
