"""ORNL EAGLE-I county outage history (Figshare, CC-BY-4.0). Annual ~1.4 GB CSVs of
15-minute customers_out by county. Each new or changed year is streamed through DuckDB
and reduced to county-day totals; the full CSV is never stored."""
import tempfile
from pathlib import Path

import duckdb

from ingest.common import http_get, last_entry, snapshot

SOURCE_ID = "eaglei_outages"
ARTICLE = "https://api.figshare.com/v2/articles/24237376"
EXTRA_FILES = ["MCC.csv", "coverage_history.csv", "DQI.csv"]  # modeled customer counts, coverage, data quality

# 2024+ files add total_customers; earlier years have 5 columns. Types are pinned by
# name so either layout parses, and the denominator is kept when present.
READ = ("read_csv('{url}', header=true, "
        "types={{'fips_code':'VARCHAR','customers_out':'DOUBLE','run_start_time':'TIMESTAMP'}})")
COUNTY_DAY_SQL = """
COPY (
  SELECT lpad(fips_code, 5, '0') AS fips,
         CAST(run_start_time AS DATE) AS day,
         SUM(customers_out) * 0.25 AS customer_hours_out,  -- 15-minute intervals
         MAX(customers_out) AS max_customers_out,
         COUNT(*) AS intervals_reported,
         {total_customers} AS total_customers
  FROM {read}
  GROUP BY 1, 2 ORDER BY 1, 2
) TO '{out}' (FORMAT parquet, COMPRESSION zstd)
"""


def run(years: list[int] | None = None) -> bool:
    files = {f["name"]: f for f in http_get(ARTICLE).json()["files"]}
    changed, failed = False, []
    for name in EXTRA_FILES:
        changed |= snapshot(SOURCE_ID, http_get(files[name]["download_url"]).content, name) is not None
    for name, f in sorted(files.items()):
        if not (name.startswith("eaglei_outages_") and name.endswith(".csv")):
            continue
        year = int(name[len("eaglei_outages_"):-4])
        if years and year not in years:
            continue
        out_name = f"county_day_{year}.parquet"
        prev = last_entry(SOURCE_ID, out_name)
        if prev and prev.get("upstream_md5") == f["computed_md5"]:
            continue
        try:
            changed |= _county_day(f, out_name, year)
        except Exception as e:  # keep processing other years; report at the end
            failed.append(f"{year}: {str(e).splitlines()[0]}")
    if failed:
        raise RuntimeError("EAGLE-I years failed: " + "; ".join(failed))
    return changed


def _county_day(f: dict, out_name: str, year: int) -> bool:
    """Stream one year's CSV from Figshare and snapshot its county-day aggregate."""
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / out_name
        con = duckdb.connect()
        con.execute("SET enable_progress_bar = false")
        read = READ.format(url=f["download_url"])
        cols = {r[0] for r in con.execute(f"DESCRIBE SELECT * FROM {read} LIMIT 1").fetchall()}
        total = "MAX(total_customers)" if "total_customers" in cols else "CAST(NULL AS DOUBLE)"
        con.execute(COUNTY_DAY_SQL.format(read=read, out=out, total_customers=total))
        rows = con.execute(f"SELECT count(*) FROM '{out}'").fetchone()[0]
        snapshot(SOURCE_ID, out.read_bytes(), out_name, {"upstream_md5": f["computed_md5"], "year": year, "rows": rows})
    return True
