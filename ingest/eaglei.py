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

COUNTY_DAY_SQL = """
COPY (
  SELECT lpad(CAST(fips_code AS VARCHAR), 5, '0') AS fips,
         CAST(run_start_time AS DATE) AS day,
         SUM(customers_out) * 0.25 AS customer_hours_out,  -- 15-minute intervals
         MAX(customers_out) AS max_customers_out,
         COUNT(*) AS intervals_reported
  FROM read_csv('{url}', header=true, columns={{'fips_code':'VARCHAR','county':'VARCHAR','state':'VARCHAR',
                'customers_out':'DOUBLE','run_start_time':'TIMESTAMP'}})
  GROUP BY 1, 2 ORDER BY 1, 2
) TO '{out}' (FORMAT parquet, COMPRESSION zstd)
"""


def run(years: list[int] | None = None) -> bool:
    files = {f["name"]: f for f in http_get(ARTICLE).json()["files"]}
    changed = False
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
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / out_name
            con = duckdb.connect()
            con.execute("SET enable_progress_bar = false")
            con.execute(COUNTY_DAY_SQL.format(url=f["download_url"], out=out))
            rows = con.execute(f"SELECT count(*) FROM '{out}'").fetchone()[0]
            snapshot(SOURCE_ID, out.read_bytes(), out_name, {"upstream_md5": f["computed_md5"], "year": year, "rows": rows})
        changed = True
    return changed
