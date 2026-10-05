"""Census cartographic boundary counties (1:500k). The county spine for spatial joins.
Note: from 2022 Census uses Connecticut planning regions (09110-09190) in place of the
8 legacy CT counties that EIA and ORNL still report; see transform/spine.py."""
from ingest.common import http_get, snapshot

SOURCE_ID = "census_counties"
VINTAGE = 2024
URL = f"https://www2.census.gov/geo/tiger/GENZ{VINTAGE}/shp/cb_{VINTAGE}_us_county_500k.zip"


def run() -> bool:
    return snapshot(SOURCE_ID, http_get(URL).content, URL.rsplit("/", 1)[1], {"vintage": VINTAGE}) is not None
