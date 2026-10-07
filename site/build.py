"""Build the public site into site/dist from site/data exports, analysis results, and
docs/methods.md. Pages: Findings (index), Map, Your utility, Methods.
Usage: uv run python site/build.py"""
import html
import json
import re
import shutil
import sys
from pathlib import Path

import markdown

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DATA, TEMPLATES, DIST = HERE / "data", HERE / "templates", HERE / "dist"
sys.path.insert(0, str(HERE / "prototype"))
import build_findings  # noqa: E402  (payload for the findings page)

REPO = "https://github.com/yottachem/grid-impact"
PAGES = [("index.html", "Findings"), ("map.html", "Map"), ("utility.html", "Your utility"), ("methods.html", "Methods")]
FONTS = ('<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
         '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Barlow+Semi+Condensed:wght@500;600'
         '&family=Public+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap">')
BASE_CSS = """
:root { --bg:#f5f7f9; --surface:#fff; --fg:#11161d; --muted:#586271; --line:#d8dee6; --grid:#e8ecf1;
  --s1:#2a78d6; --s2:#eb6834; --s3:#1baf7a; --s4:#eda100;
  --font-display:"Barlow Semi Condensed","Arial Narrow","Helvetica Neue",Arial,sans-serif;
  --font-body:"Public Sans","Helvetica Neue",Arial,sans-serif; --font-data:"IBM Plex Mono",ui-monospace,Menlo,monospace; color-scheme: light; }
@media (prefers-color-scheme: dark) { :root { --bg:#11151a; --surface:#181d23; --fg:#eef1f4; --muted:#9aa5b2; --line:#2b323b; --grid:#232a32;
  --s1:#3987e5; --s2:#d95926; --s3:#199e70; --s4:#c98500; color-scheme: dark; } }
* { box-sizing: border-box; } html { -webkit-text-size-adjust: 100%; }
body { margin: 0; background: var(--bg); color: var(--fg); font: 15px/1.55 var(--font-body); }
[hidden] { display: none !important; } img { max-width: 100%; }
.nav { position: sticky; top: 0; z-index: 10; background: var(--surface); border-bottom: 1px solid var(--line); }
.nav-in { max-width: 1120px; margin: 0 auto; padding-inline: 20px; display: flex; flex-wrap: wrap; align-items: center; gap: 4px 18px; min-height: 52px; }
.brand { font: 600 18px/1 var(--font-display); color: var(--fg); text-decoration: none; margin-right: auto; }
.nav a.l { color: var(--muted); text-decoration: none; font-size: 14px; padding-block: 14px; border-bottom: 2px solid transparent; }
.nav a.l[aria-current="page"] { color: var(--fg); border-bottom-color: var(--s1); }
.nav a:focus-visible { outline: 2px solid var(--s1); outline-offset: 2px; }
.foot { border-top: 1px solid var(--line); margin-top: 24px; }
.foot-in { max-width: 1120px; margin: 0 auto; padding-inline: 20px; padding-block: 18px 28px; font-size: 13px; color: var(--muted); display: grid; gap: 4px; }
.foot a { color: inherit; }
.prose { max-width: 820px; margin: 0 auto; padding-inline: 20px; padding-block: 28px 48px; }
.prose h1 { font: 600 38px/1.05 var(--font-display); margin: 0 0 12px; }
.prose h2 { font: 600 24px/1.15 var(--font-display); margin: 32px 0 8px; }
.prose p, .prose li { max-width: 72ch; } .prose code { font: 13px var(--font-data); }
.prose table { border-collapse: collapse; font-size: 14px; display: block; overflow-x: auto; margin: 8px 0 16px; }
.prose th, .prose td { border-bottom: 1px solid var(--line); padding: 7px 10px; text-align: left; vertical-align: top; }
.prose th { font: 500 11px/1.2 var(--font-data); text-transform: uppercase; letter-spacing: .06em; color: var(--muted); }
.prose a { color: var(--s1); }
"""


def shell(page: str, title: str, body: str, footer: str, description: str) -> str:
    cur = ' aria-current="page"'
    nav = "".join(f'<a class="l" href="{f}"{cur if f == page else ""}>{n}</a>' for f, n in PAGES)
    nav += f'<a class="l" href="{REPO}">Code &amp; data</a>'
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">'
            f'<title>{html.escape(title)} · Grid Impact Tracker</title><meta name="description" content="{html.escape(description)}">'
            f'{FONTS}<style>{BASE_CSS}</style></head><body>'
            f'<nav class="nav" aria-label="Site"><div class="nav-in"><a class="brand" href="index.html">Grid Impact Tracker</a>{nav}</div></nav>'
            f'<main>{body}</main><footer class="foot"><div class="foot-in">{footer}</div></footer></body></html>')


def split_template(t: str) -> tuple[str, str]:
    """Pull the <title> out of an artifact-style template; drop its own font links."""
    title = re.search(r"<title>(.*?)</title>", t).group(1)
    t = re.sub(r"<title>.*?</title>", "", t, count=1)
    t = re.sub(r'<link rel="(preconnect|stylesheet)"[^>]*fonts\.(googleapis|gstatic)\.com[^>]*>', "", t)
    return title, t


def footer(meta: dict, price_through: str) -> str:
    s = meta["sources"]
    fresh = lambda k: s.get(k, {}).get("last_new_data") or "—"
    return (f"<span>Updated automatically when sources publish new data. Last build {meta['built'][:10]}. "
            f"Residential prices through {price_through}; data center sites as of {fresh('fractracker_datacenters')}; "
            f"PJM auctions through 2028/29.</span>"
            f"<span>Data: EIA, PJM, PJM Independent Market Monitor, BLS, NOAA, Census, ORNL; data center locations from "
            f"FracTracker Alliance (non-commercial use), PNNL IM3, © OpenStreetMap contributors, PeeringDB. "
            f'<a href="methods.html">Methods and licenses</a> · <a href="{REPO}">Source code</a></span>')


def price_month() -> str:
    try:
        import pandas as pd
        return pd.read_parquet(ROOT / "data" / "marts" / "utility_month.parquet").period.max().strftime("%B %Y")
    except Exception:
        return "latest EIA release"


def main() -> None:
    if DIST.exists():
        shutil.rmtree(DIST)
    (DIST / "data").mkdir(parents=True)
    for f in DATA.glob("*.json"):
        shutil.copy(f, DIST / "data" / f.name)
    shutil.copy(DATA / "README.md", DIST / "data" / "README.md")
    meta = json.loads((DATA / "meta.json").read_text())
    pm = price_month()
    foot = footer(meta, pm)

    # Findings
    payload, n_units = build_findings.payload()
    title, t = split_template((TEMPLATES / "findings.html.tmpl").read_text())
    t = t.replace("__DATA__", json.dumps(payload, separators=(",", ":"))).replace("__NUNITS__", str(n_units))
    t = t.replace("Grid Impact Tracker · findings draft", "Grid Impact Tracker · findings")
    t = t.replace("Draft built", "Built")
    (DIST / "index.html").write_text(shell("index.html", title, t, foot,
        "How US data center growth is affecting residential electricity bills, from utility data 2015 to present."))

    # Map (MapLibre; tract and county layers load from data/*.json at runtime)
    sites = json.loads((DATA / "sites_open.json").read_text()) + json.loads((DATA / "sites_fractracker.json").read_text())
    title, t = split_template((TEMPLATES / "map.html.tmpl").read_text())
    t = t.replace("__SITES__", json.dumps(sites, separators=(",", ":")))
    (DIST / "map.html").write_text(shell("map.html", title, t, foot,
        "Zoomable map of US data centers with neighborhood electricity costs and county data center load per household."))

    # Your utility
    title, t = split_template((TEMPLATES / "utility.html.tmpl").read_text())
    t = (t.replace("__USAGE__", (DATA / "utility_usage_bill.json").read_text())
          .replace("__EXPOSURE__", (DATA / "utility_exposure.json").read_text())
          .replace("__CAPACITY__", (DATA / "capacity_household_cost.json").read_text())
          .replace("__REALMONTH__", html.escape(meta.get("real_dollars_of", "the latest CPI month"))))
    (DIST / "utility.html").write_text(shell("utility.html", title, t, foot,
        "Residential price, usage, and bill by utility, adjusted for inflation, with data center load in each territory."))

    # Methods (methods.md + data licenses)
    md = (ROOT / "docs" / "methods.md").read_text().replace("# Methods (working draft)", "# Methods")
    md = re.sub(r"\*Records each modeling decision.*?\*\n", "", md)
    md += "\n\n## Data downloads and licenses\n\n" + (DATA / "README.md").read_text().split("\n", 2)[2].replace("](", "](data/")
    md += "\n\nFiles: " + ", ".join(f"[{f.name}](data/{f.name})" for f in sorted(DATA.glob("*.json"))) + "\n"
    body = '<article class="prose">' + markdown.markdown(md, extensions=["tables"]) + "</article>"
    (DIST / "methods.html").write_text(shell("methods.html", "Methods", body, foot,
        "Sources, modeling decisions, and known limitations of the Grid Impact Tracker."))
    (DIST / ".nojekyll").write_text("")
    for f in sorted(DIST.glob("*.html")):
        print(f"wrote site/dist/{f.name}  {f.stat().st_size / 1024:,.0f} KB")


if __name__ == "__main__":
    main()
