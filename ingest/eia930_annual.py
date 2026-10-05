"""Annual energy (sum of daily demand) by ISO/RTO from EIA-930, full calendar years.
Used to turn total capacity auction cost into a cost per kWh. One paged query covers
all RTOs and years (~4 requests), which keeps within the DEMO_KEY limit locally."""
import json
import os
from collections import defaultdict
from datetime import date

from ingest.common import http_get, snapshot

SOURCE_ID = "eia930_annual"
URL = "https://api.eia.gov/v2/electricity/rto/daily-region-data/data/"
RTOS = ["PJM", "MISO", "ERCO", "CISO", "NYIS", "ISNE", "SWPP"]
FIRST_YEAR = 2019
PAGE = 5000


def run() -> bool:
    key = os.environ.get("EIA_API_KEY") or "DEMO_KEY"
    last = date.today().year - 1
    params = {"api_key": key, "frequency": "daily", "data[0]": "value", "facets[type][]": "D",
              "facets[respondent][]": RTOS, "facets[timezone][]": "Eastern",
              "start": f"{FIRST_YEAR}-01-01", "end": f"{last}-12-31", "length": PAGE}
    totals, days, offset = defaultdict(float), defaultdict(int), 0
    while True:
        resp = http_get(URL, params={**params, "offset": offset}).json()["response"]
        for r in resp["data"]:
            if r.get("value") not in (None, ""):
                k = (r["respondent"], int(r["period"][:4]))
                totals[k] += float(r["value"])
                days[k] += 1
        offset += PAGE
        if offset >= int(resp["total"]):
            break
    rows = [{"rto": k[0], "year": k[1], "days": days[k], "energy_mwh": round(v)} for k, v in sorted(totals.items())]
    return snapshot(SOURCE_ID, json.dumps(rows, separators=(",", ":")).encode(), "annual_energy.json") is not None
