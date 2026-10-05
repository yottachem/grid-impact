"""EIA-860M monthly generator inventory: operating, planned, retired, and canceled units.
EIA's index lists future months that redirect, so probe backward from the current month
without following redirects and take the newest file that exists."""
from datetime import date

import requests

from ingest.common import USER_AGENT, http_get, snapshot

SOURCE_ID = "eia860m"
BASE = "https://www.eia.gov/electricity/data/eia860m/"
MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august",
          "september", "october", "november", "december"]


def _candidates():
    y, m = date.today().year, date.today().month
    for _ in range(6):
        for folder in ("xls", "archive/xls"):
            yield f"{folder}/{MONTHS[m - 1]}_generator{y}.xlsx", y, m
        y, m = (y, m - 1) if m > 1 else (y - 1, 12)


def run() -> bool:
    for path, y, m in _candidates():
        r = requests.head(BASE + path, headers={"User-Agent": USER_AGENT}, allow_redirects=False, timeout=60)
        if r.status_code == 200:
            content = http_get(BASE + path, timeout=300).content
            return snapshot(SOURCE_ID, content, "generators.xlsx", {"as_of": f"{y}-{m:02d}", "file": path}) is not None
    raise RuntimeError("no EIA-860M file found in the last 6 months")
