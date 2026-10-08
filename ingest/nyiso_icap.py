"""NYISO installed capacity (ICAP) spot auction results: monthly clearing prices ($/kW-month, UCAP) for
New York City, Long Island, the G-J Locality (lower Hudson Valley), and the rest of the state (NYCA).

Source: NYISO's public ICAP viewer (icappublic.nyiso.com), which has no bulk download. The viewer's
season and month lists are JSON; each month's "View Spot Auction Summary" is an HTML table, read here
for every month from Summer 2018 on. Writes one JSON file with all months; a new month (posted near the
end of the prior month) changes the snapshot."""
import json
import re
import time
from datetime import date

from ingest.common import snapshot

SOURCE_ID = "nyiso_icap"
BASE = "https://icappublic.nyiso.com"
UA = {"User-Agent": "Mozilla/5.0 (grid-impact research; https://github.com/yottachem/grid-impact)"}
FIRST_SEASON = "Summer 2018"
LOCALITIES = ["G-J Locality", "LI", "NYC", "NYCA"]


def _prices(page: str) -> dict:
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " | ", page))
    out = {}
    for loc in LOCALITIES:
        m = re.search(rf"\| {re.escape(loc)} \|.*?Price \(\$/kW-M\) \|\s*\|\s*\$([\d,.]+)", text)
        if m:
            out[loc] = float(m.group(1).replace(",", ""))
    ros = re.search(r"ROS Price Paid By LSE's \(Weighted Avg\.\) \|\s*\|\s*\$([\d,.]+)", text.replace("&#39;", "'"))
    if ros:
        out["ROS weighted"] = float(ros.group(1))
    return out


def run() -> bool:
    import requests
    s = requests.Session()
    s.headers.update(UA)
    s.get(f"{BASE}/ucap/public/auc_view_spot_selection.do", timeout=60)  # session cookie
    seasons = s.get(f"{BASE}/ucap/rest/seasons/public", timeout=60).json()["rows"]
    seasons = sorted(seasons, key=lambda r: r["startDate"][6:10] + r["startDate"][:2])
    start = next(i for i, r in enumerate(seasons) if r["description"] == FIRST_SEASON)
    today = date.today().strftime("%Y%m")
    rows = []
    for season in seasons[start:]:
        months = s.get(f"{BASE}/ucap/rest/month/public/season/{season['id']}", timeout=60).json()["rows"]
        for mo in months:
            if mo["sortableString"] > today:
                continue
            r = s.post(f"{BASE}/ucap/public/auc_view_spot_detail.do", timeout=90,
                       data={"seasonId": season["id"], "month": mo["selectableValue"], "display": "Display"})
            r.raise_for_status()
            p = _prices(r.text)
            if "NYCA" in p:  # months without a posted spot auction are skipped
                rows.append({"month": mo["sortableString"][:4] + "-" + mo["sortableString"][4:], "season": season["description"], **p})
            time.sleep(0.4)
    if not rows:
        raise ValueError("NYISO ICAP viewer returned no spot results (layout changed?)")
    content = json.dumps(rows, indent=1).encode()
    return snapshot(SOURCE_ID, content, "spot_prices.json", {"months": len(rows), "through": rows[-1]["month"]}) is not None


if __name__ == "__main__":
    print("new data:", run())
