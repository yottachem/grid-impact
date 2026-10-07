"""Census cartographic boundary tracts (1:500k) for the neighborhood cost layer: all 50
states and DC."""
from ingest.common import http_get, snapshot

SOURCE_ID = "census_tracts"
VINTAGE = 2024
# 50 states + DC (Census FIPS)
TRACT_STATES = ["01", "02", "04", "05", "06", "08", "09", "10", "11", "12", "13", "15", "16", "17", "18", "19", "20",
                "21", "22", "23", "24", "25", "26", "27", "28", "29", "30", "31", "32", "33", "34", "35", "36", "37",
                "38", "39", "40", "41", "42", "44", "45", "46", "47", "48", "49", "50", "51", "53", "54", "55", "56"]


def run() -> bool:
    changed = False
    for st in TRACT_STATES:
        name = f"cb_{VINTAGE}_{st}_tract_500k.zip"
        url = f"https://www2.census.gov/geo/tiger/GENZ{VINTAGE}/shp/{name}"
        changed |= snapshot(SOURCE_ID, http_get(url).content, name, {"vintage": VINTAGE, "state": st}) is not None
    return changed
