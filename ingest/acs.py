"""Census ACS 5-year county tables from the keyless table-based summary files (the
Census API now requires a key). Kept: households (B11001) and median household income
(B19013), county rows only."""
import io

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
        out = io.StringIO()
        out.write(f"county_fips,{col.lower()}\n")
        for line in lines[1:]:
            if line.startswith("0500000US"):
                f = line.split("|")
                out.write(f"{f[0][-5:]},{f[i]}\n")
        changed |= snapshot(SOURCE_ID, out.getvalue().encode(), f"{table}_county.csv", {"vintage": VINTAGE}) is not None
    return changed
