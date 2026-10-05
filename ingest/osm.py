"""OpenStreetMap data center features in the US via Overpass (nodes, ways, relations
tagged telecom=data_center or building=data_center; ways/relations reduced to centers)."""
import json

import requests

from ingest.common import USER_AGENT, snapshot

SOURCE_ID = "osm_datacenters"
URL = "https://overpass-api.de/api/interpreter"
QUERY = """[out:json][timeout:300];
area["ISO3166-1"="US"][admin_level=2]->.us;
(nwr["telecom"="data_center"](area.us);nwr["building"="data_center"](area.us););
out center tags;"""


def run() -> bool:
    r = requests.post(URL, data={"data": QUERY}, headers={"User-Agent": USER_AGENT}, timeout=360)
    r.raise_for_status()
    rows = []
    for e in r.json()["elements"]:
        c = e.get("center", e)
        rows.append({"osm_type": e["type"], "osm_id": e["id"], "lat": c.get("lat"), "lon": c.get("lon"), "tags": e.get("tags", {})})
    rows.sort(key=lambda x: (x["osm_type"], x["osm_id"]))
    content = json.dumps(rows, separators=(",", ":"), sort_keys=True).encode()
    return snapshot(SOURCE_ID, content, "osm_datacenters_us.json", {"rows": len(rows)}) is not None
