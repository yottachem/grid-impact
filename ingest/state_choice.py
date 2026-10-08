"""State reports of how many residential customers buy supply from competitive suppliers or
aggregation programs, by utility. EIA's monthly survey does not split these customers by utility
(see analysis/coverage.py); these fill the gap where a state publishes them.

- IL: Illinois Commerce Commission monthly switching workbooks (ComEd, Ameren Illinois)
- PA: PA PUC PAPowerSwitch monthly statistics PDF (linked from the PAPowerSwitch home page)
- NJ: NJ Board of Public Utilities monthly electric switching statistics PDF

Massachusetts publishes the same data (DOER customer choice data) but mass.gov blocks automated
downloads; that file is added by hand (see reference/README)."""
import re
from datetime import date

import requests

from ingest.common import http_get, snapshot

SOURCE_ID = "state_choice"
UA = {"User-Agent": "Mozilla/5.0 (grid-impact research; https://github.com/yottachem/grid-impact)"}


def _get(url: str) -> bytes | None:
    try:
        r = http_get(url, retries=2, headers=UA)
    except requests.HTTPError as e:
        if e.response is not None and e.response.status_code == 404:
            return None
        raise
    return r.content


def illinois() -> list[bool]:
    page = http_get("https://icc.illinois.gov/industry-reports/electric-switching-statistics", headers=UA).text
    year = date.today().year
    out = []
    for href in re.findall(r'href="([^"]+\.xlsx)"', page):
        name = href.rsplit("/", 1)[1]
        if str(year) not in name and str(year - 1) not in name:
            continue
        content = _get("https://icc.illinois.gov" + href.replace(" ", "%20") if href.startswith("/") else href)
        if content:
            out.append(snapshot(SOURCE_ID, content, "IL_" + name.replace(" ", "_")) is not None)
    if not out:
        raise ValueError("ICC switching page: no workbooks found (layout changed?)")
    return out


def pennsylvania() -> list[bool]:
    page = http_get("https://www.papowerswitch.com/", headers=UA).text
    links = re.findall(r'href="([^"]*paps_numbers(\d{6})\.pdf)"', page)
    if not links:
        raise ValueError("PAPowerSwitch home page: statistics PDF link not found (layout changed?)")
    href, mmddyy = links[0]
    content = _get("https://www.papowerswitch.com" + href if href.startswith("/") else href)
    return [snapshot(SOURCE_ID, content, f"PA_paps_numbers_20{mmddyy[4:]}-{mmddyy[:2]}.pdf") is not None] if content else []


def new_jersey() -> list[bool]:
    out, d = [], date.today()
    for back in range(0, 4):  # the latest few months; BPU posts with a lag
        y, m = (d.year, d.month - back) if d.month > back else (d.year - 1, d.month - back + 12)
        name = f"{date(y, m, 1):%B} {y} Electric.pdf"
        content = _get("https://www.nj.gov/bpu/pdf/energy/" + name.replace(" ", "%20"))
        if content and content[:4] == b"%PDF":
            out.append(snapshot(SOURCE_ID, content, f"NJ_{y}-{m:02d}_Electric.pdf") is not None)
    return out


def run() -> bool:
    changed = []
    for fn in (illinois, pennsylvania, new_jersey):
        changed += fn()
    return any(changed)


if __name__ == "__main__":
    print("new data:", run())
