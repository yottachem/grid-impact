"""NOAA nClimDiv monthly heating and cooling degree days by county (contiguous US).
File names carry the processing date, read from procdate.txt."""
from ingest.common import http_get, snapshot

SOURCE_ID = "noaa_degree_days"
BASE = "https://www.ncei.noaa.gov/monitoring-content/data/us/climdiv/monthly/current/"


def run() -> bool:
    proc = http_get(BASE + "procdate.txt").text.strip()
    changed = False
    for kind in ("hddccy", "cddccy"):
        name = f"climdiv-{kind}-v1.0.0-{proc}"
        changed |= snapshot(SOURCE_ID, http_get(BASE + name).content, f"{kind}.txt", {"procdate": proc}) is not None
    return changed
