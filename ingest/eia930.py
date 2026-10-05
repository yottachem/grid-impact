"""EIA-930 daily demand by balancing authority (EIA API v2). Pulls the trailing
window so provisional values that EIA revises are picked up."""
import json
import os
from datetime import date, timedelta

from ingest.common import http_get, snapshot

SOURCE_ID = "eia930_daily"
URL = "https://api.eia.gov/v2/electricity/rto/daily-region-data/data/"
WINDOW_DAYS = 45
PAGE = 5000


def run() -> bool:
    key = os.environ.get("EIA_API_KEY", "DEMO_KEY")
    start = (date.today() - timedelta(days=WINDOW_DAYS)).isoformat()
    rows, offset = [], 0
    while True:
        params = {
            "api_key": key,
            "frequency": "daily",
            "data[0]": "value",
            "facets[type][]": "D",
            "facets[timezone][]": "Eastern",
            "start": start,
            "sort[0][column]": "period",
            "sort[0][direction]": "asc",
            "offset": offset,
            "length": PAGE,
        }
        resp = http_get(URL, params=params).json()["response"]
        rows += resp["data"]
        offset += PAGE
        if offset >= int(resp["total"]):
            break
    rows.sort(key=lambda r: (r["period"], r["respondent"]))
    content = json.dumps(rows, separators=(",", ":")).encode()
    latest = max((r["period"] for r in rows), default=None)
    return snapshot(SOURCE_ID, content, "daily_demand.json", {"rows": len(rows), "data_through": latest}) is not None
