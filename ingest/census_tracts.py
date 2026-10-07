"""Census cartographic boundary tracts (1:500k) for the states in the neighborhood cost
layer. Add a state's FIPS to TRACT_STATES to extend the layer."""
from ingest.common import http_get, snapshot

SOURCE_ID = "census_tracts"
VINTAGE = 2024
TRACT_STATES = ["51", "24", "11"]  # Virginia, Maryland, DC


def run() -> bool:
    changed = False
    for st in TRACT_STATES:
        name = f"cb_{VINTAGE}_{st}_tract_500k.zip"
        url = f"https://www2.census.gov/geo/tiger/GENZ{VINTAGE}/shp/{name}"
        changed |= snapshot(SOURCE_ID, http_get(url).content, name, {"vintage": VINTAGE, "state": st}) is not None
    return changed
