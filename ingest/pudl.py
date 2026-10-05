"""PUDL (Catalyst Cooperative) stable-release tables for annual EIA-861 history."""
from ingest.common import http_get, snapshot

SOURCE_ID = "pudl_eia861_annual"
BASE = "https://s3.us-west-2.amazonaws.com/pudl.catalyst.coop/stable/"
TABLES = [
    "core_eia861__yearly_sales",
    "out_eia861__yearly_utility_service_territory",
    "core_eia861__yearly_reliability",
    "core_eia__codes_balancing_authorities",
]


def run() -> bool:
    changed = False
    for t in TABLES:
        content = http_get(f"{BASE}{t}.parquet").content
        changed |= snapshot(SOURCE_ID, content, f"{t}.parquet", {"table": t}) is not None
    return changed
