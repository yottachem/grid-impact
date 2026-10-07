"""Census ACS 5-year tables from the keyless table-based summary files (the Census API
now requires a key). Kept: households (B11001) and median household income (B19013),
for all counties and for tracts in the neighborhood cost layer's states."""
import io

from ingest.census_tracts import TRACT_STATES
from ingest.common import http_get, snapshot

SOURCE_ID = "acs_county"
VINTAGE = 2024
BASE = f"https://www2.census.gov/programs-surveys/acs/summary_file/{VINTAGE}/table-based-SF/data/5YRData/"
TABLES = {"b11001": "B11001_E001", "b19013": "B19013_E001"}  # households, median household income


def run() -> bool:
    changed = False
    for table, col in TABLES.items():
        text = http_get(f"{BASE}acsdt5y{VINTAGE}-{table}.dat", timeout=300).text
        lines = text.splitlines()
        head = lines[0].split("|")
        i = head.index(col)
        county, tract = io.StringIO(), io.StringIO()
        county.write(f"county_fips,{col.lower()}\n")
        tract.write(f"tract_geoid,{col.lower()}\n")
        tract_prefixes = tuple(f"1400000US{st}" for st in TRACT_STATES)
        for line in lines[1:]:
            if line.startswith("0500000US"):
                f = line.split("|")
                county.write(f"{f[0][-5:]},{f[i]}\n")
            elif line.startswith(tract_prefixes):
                f = line.split("|")
                tract.write(f"{f[0][-11:]},{f[i]}\n")
        changed |= snapshot(SOURCE_ID, county.getvalue().encode(), f"{table}_county.csv", {"vintage": VINTAGE}) is not None
        changed |= snapshot(SOURCE_ID, tract.getvalue().encode(), f"{table}_tract.csv", {"vintage": VINTAGE}) is not None
    return changed
