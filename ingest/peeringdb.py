"""PeeringDB colocation facilities in the US (lat/lon, operator, address)."""
import json
import os

from ingest.common import http_get, snapshot

SOURCE_ID = "peeringdb_facilities"
URL = "https://www.peeringdb.com/api/fac"


def run() -> bool:
    key = os.environ.get("PEERINGDB_API_KEY")
    headers = {"Authorization": f"Api-Key {key}"} if key else {}
    data = http_get(URL, params={"country": "US"}, headers=headers).json()["data"]
    keep = ["id", "org_name", "name", "city", "state", "zipcode", "latitude", "longitude", "status", "updated"]
    rows = sorted(({k: d.get(k) for k in keep} for d in data), key=lambda r: r["id"])
    content = json.dumps(rows, separators=(",", ":")).encode()
    return snapshot(SOURCE_ID, content, "facilities_us.json", {"rows": len(rows)}) is not None
