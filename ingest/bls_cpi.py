"""BLS CPI-U (not seasonally adjusted): all items and electricity for the US, the four
Census regions, and each published metro area. Keyless API v1 (BLS bulk files block
automated clients): 25 series and 10 years per request, 25 requests per day."""
import json
from datetime import date

from ingest.common import http_post, snapshot

SOURCE_ID = "bls_cpi"
URL = "https://api.bls.gov/publicAPI/v1/timeseries/data/"
FIRST_YEAR = 2015
METROS = {  # CPI area code: name
    "S11A": "Boston", "S12A": "New York", "S12B": "Philadelphia", "S23A": "Chicago", "S23B": "Detroit",
    "S24A": "Minneapolis", "S24B": "St. Louis", "S35A": "Washington DC", "S35B": "Miami", "S35C": "Atlanta",
    "S35D": "Tampa", "S35E": "Baltimore", "S37A": "Dallas-Fort Worth", "S37B": "Houston", "S48A": "Phoenix",
    "S48B": "Denver", "S49A": "Los Angeles", "S49B": "San Francisco", "S49C": "Riverside", "S49D": "Seattle",
    "S49E": "San Diego", "S49F": "Urban Hawaii", "S49G": "Urban Alaska",
}
REGIONS = {"0000": "U.S. city average", "0100": "Northeast", "0200": "Midwest", "0300": "South", "0400": "West"}
SERIES = ([f"CUUR{a}SA0" for a in REGIONS] + [f"CUUR{a}SEHF01" for a in REGIONS]
          + [f"CUUR{a}SEHF01" for a in METROS])


def run() -> bool:
    end = date.today().year
    windows = [(y, min(y + 9, end)) for y in range(FIRST_YEAR, end + 1, 10)]
    rows, missing = [], set(SERIES)
    for i in range(0, len(SERIES), 25):
        chunk = SERIES[i:i + 25]
        for start, stop in windows:
            body = {"seriesid": chunk, "startyear": str(start), "endyear": str(stop)}
            resp = http_post(URL, json=body).json()
            if resp.get("status") != "REQUEST_SUCCEEDED":
                raise RuntimeError(f"BLS API: {resp.get('status')} {resp.get('message')}")
            for s in resp["Results"]["series"]:
                for d in s["data"]:
                    # "-" marks months a bimonthly metro is not surveyed
                    if d["period"].startswith("M") and d["period"] != "M13" and d["value"] not in ("-", ""):
                        rows.append({"series_id": s["seriesID"], "year": int(d["year"]),
                                     "month": int(d["period"][1:]), "value": float(d["value"])})
                        missing.discard(s["seriesID"])
    rows.sort(key=lambda r: (r["series_id"], r["year"], r["month"]))
    meta = {"areas": {**REGIONS, **METROS}, "series_without_data": sorted(missing)}
    content = json.dumps({"meta": meta, "data": rows}, separators=(",", ":")).encode()
    latest = max((f"{r['year']}-{r['month']:02d}" for r in rows), default=None)
    return snapshot(SOURCE_ID, content, "cpi.json", {"rows": len(rows), "data_through": latest}) is not None
