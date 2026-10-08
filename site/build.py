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
from analysis import narrative  # noqa: E402  (build_findings puts the repo root on sys.path)

REPO = "https://github.com/yottachem/grid-impact"
PAGES = [("index.html", "Map"), ("findings.html", "Findings"), ("utility.html", "Your utility"), ("methods.html", "Methods")]
FRIENDLY_DATE = lambda d: __import__("datetime").date.fromisoformat(d).strftime("%b %-d, %Y") if d else "—"
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
.prose.wide { max-width: 1060px; }
.src-pub { font-size: 12px; color: var(--muted); }
.badge { display: inline-flex; align-items: center; gap: 6px; font: 500 11px/1 var(--font-data); text-transform: uppercase; letter-spacing: .05em; }
.badge i { width: 8px; height: 8px; border-radius: 50%; display: inline-block; }
.status-line { color: var(--fg); }
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


def status_line(meta: dict) -> str:
    """One-line data status for every page footer, linking to the full status page."""
    sm, src = meta["summary"], meta["sources"]
    late = f"{len(sm['late'])} late" if sm["late"] else "all current"
    return (f'<span class="status-line"><a href="status.html">Data status</a>: {sm["sources"]} sources tracked, {late} · '
            f'newest data {FRIENDLY_DATE(sm["newest_data"])} ({html.escape(src[sm["newest_source"]]["name"].split(" (")[0])}) · '
            f'{len(sm["updated_last_7_days"])} updated in the past 7 days · {len(sm["added_last_30_days"])} added in the past 30 days</span>')


def quality_section() -> str:
    """Data center data quality figures from transform/datacenter_qa.py and a national benchmark."""
    qa_path = ROOT / "data" / "marts" / "datacenter_qa.json"
    if not qa_path.exists():
        return ""
    q = json.loads(qa_path.read_text())
    bench = ""
    try:
        import pandas as pd
        s = pd.read_parquet(ROOT / "data" / "marts" / "datacenter_sites.parquet")
        op = s[(s.status_group == "operating") & ~s.duplicate].mw_est.sum() / 1000
        lo, hi = op * 0.5 * 8.76, op * 0.7 * 8.76
        lbnl = pd.read_csv(ROOT / "reference" / "context_facts.csv", dtype=str).set_index("fact_id").loc["lbnl_us_dc_twh_2023"]
        bench = (f"<p><b>Consistency check.</b> Operating sites total about {op:,.0f} GW of estimated capacity. At typical 50-70% "
                 f"utilization that is roughly {lo:,.0f}-{hi:,.0f} TWh a year, versus Lawrence Berkeley National Laboratory's estimate "
                 f"of {float(lbnl.value):,.0f} TWh of US data center use in 2023 (December 2024 report). The gap is expected: listed capacity is often "
                 f"full planned build-out, and use has grown since 2023. Totals are best read as upper bounds.</p>")
    except Exception:
        pass
    return (f"<h2>Data center data quality</h2>"
            f"<table><tbody>"
            f"<tr><td>Sites shown (operating, under construction, proposed)</td><td>{q['sites']:,}</td></tr>"
            f"<tr><td>Power reported by source</td><td>{q['mw_reported']:,}</td></tr>"
            f"<tr><td>Power estimated from floor or land area</td><td>{q['mw_estimated']:,}</td></tr>"
            f"<tr><td>No size data (shown, not in MW totals)</td><td>{q['mw_unknown']:,}</td></tr>"
            f"<tr><td>Network facilities (hidden by default)</td><td>{q['network_facilities']:,}</td></tr>"
            f"<tr><td>Duplicate listings merged</td><td>{q['duplicates_removed']:,} ({q['duplicate_mw_removed']:,} MW removed)</td></tr>"
            f"<tr><td>Nearby similar pairs confirmed as separate buildings by rule</td><td>{q['pairs_distinct']:,}</td></tr>"
            f"<tr><td>Pairs settled by manual review (with evidence)</td><td>{q.get('pairs_reviewed', 0):,} ({q.get('review_records_removed', 0):,} records, {q.get('review_mw_removed', 0):,} MW removed)</td></tr>"
            f"<tr><td>Nearby similar pairs pending review</td><td>{q['pairs_for_review']:,} (up to {q['review_mw_upper_bound']:,} MW could be double counted)</td></tr>"
            f"</tbody></table>"
            f"<p>Pairs pending review are nearby records with a shared operator or similar name that the automatic rules could "
            f"not settle, such as a campus total listed alongside its buildings, or an operating building next to a proposed "
            f"expansion. They are kept, so some double counting may remain. "
            f'<a href="{html.escape(build_findings.feedback_url("Map"))}">Report a correction</a> (no account needed), or '
            f'<a href="https://github.com/yottachem/grid-impact/issues/new?template=data-correction.yml">open a GitHub issue</a>.</p>'
            + bench)


def analysis_section() -> str:
    """When the analysis last ran and which parts update automatically vs. by hand."""
    run_path = ROOT / "analysis" / "results" / "run.json"
    if not run_path.exists():
        return ""
    r = json.loads(run_path.read_text())
    month = __import__("datetime").datetime.strptime(r["prices_through"], "%Y-%m").strftime("%B %Y")
    return (f"<h2>Analysis</h2><table><tbody>"
            f"<tr><td>Analysis last run</td><td>{r['ran_at'][:16].replace('T', ' ')} UTC</td></tr>"
            f"<tr><td>Residential prices through</td><td>{month}</td></tr>"
            f"<tr><td>PJM capacity auctions through</td><td>{html.escape(r['capacity_auctions_through'])} (entered by hand)</td></tr>"
            f"<tr><td>Data center share of capacity cost through</td><td>{html.escape(r['dc_attribution_through'])} (entered by hand)</td></tr>"
            f"</tbody></table>"
            f"<p>The analysis reruns in full whenever any source brings new data: capacity cost per home, the regressions, the "
            f"case studies, county and utility data center load, and neighborhood costs. Findings page figures and wording come "
            f"from that run. Results change mainly when EIA publishes a new month of utility sales (about two months after the "
            f"month ends). Three inputs are entered by hand when published, so they lag until then: PJM capacity auction results, "
            f"the market monitor's data center share, and the curated utility tables. The Methods page describes the method; its "
            f"example figures carry an as-of date.</p>")


def claims_section(nar: dict) -> str:
    """How the findings wording is checked, and anything currently under review."""
    flagged = nar["flagged"]
    rows = "".join(f"<tr><td><code>{html.escape(c)}</code></td><td>{nar['claims'][c]['where'].title()}</td>"
                   f"<td>{html.escape(nar['claims'][c]['reason'] or '')}</td></tr>" for c in flagged)
    due = "".join(f"<tr><td><code>{html.escape(f['fact'])}</code></td><td>{html.escape(f['statement'])}</td>"
                  f"<td>{html.escape(f['review_by'])}</td></tr>" for f in nar["facts_due"])
    return (f"<h2>Findings checks</h2>"
            f"<p>Each statement on the Findings and Methods pages is stored with the condition it rests on (for example, "
            f"that a confidence interval excludes zero) and with plausibility ranges for its numbers. Every analysis run "
            f"checks all {nar['n_claims']} statements. A statement that no longer fits the data is shown as current figures "
            f"without interpretation, marked under review, and opened as a GitHub issue until it is rewritten and reviewed. "
            f"Last check: {narrative.fmt(nar['run_date'], 'date')}.</p>"
            + (f"<table><thead><tr><th>Statement</th><th>Page</th><th>Why</th></tr></thead><tbody>{rows}</tbody></table>"
               if flagged else "<p><b>All statements fit the current data.</b></p>")
            + (f"<p>Hand-entered facts past their review date:</p><table><thead><tr><th>Fact</th><th>Statement</th><th>Review by</th>"
               f"</tr></thead><tbody>{due}</tbody></table>" if due else ""))


def methods_markdown(nar: dict) -> str:
    """docs/methods.md with {{claim:id}} statements and {{value:format}} figures filled in from the latest run."""
    md = (ROOT / "docs" / "methods.md").read_text().replace("# Methods (working draft)", "# Methods")
    v = nar["values"]
    def claim(cid: str) -> str:
        c = nar["claims"][cid]
        return c["text"] if c["status"] == "ok" else (c["text"] + " *(Under review: the latest data no longer fits the earlier wording.)*")
    md = re.sub(r"\{\{claim:([a-z0-9_]+)\}\}", lambda m: claim(m.group(1)), md)
    md = re.sub(r"\{\{([a-z][a-z0-9_.]*)(?::([a-z0-9]+))?\}\}", lambda m: narrative.fmt(v[m.group(1)], m.group(2)), md)
    return md


def status_page(meta: dict, nar: dict) -> str:
    rows = sorted(meta["sources"].items(), key=lambda kv: (kv[1]["last_new_data"] or "", kv[1]["added"]), reverse=True)
    badge = {"current": ("Current", "var(--s3)"), "late": ("Late", "var(--s2)"), "pending": ("Not yet fetched", "var(--muted)")}
    trs = "".join(
        f"<tr><td>{html.escape(v['name'])}<br><span class='src-pub'>{html.escape(v.get('publisher') or '')}</span></td>"
        f"<td><span class='badge'><i style='background:{badge[v['status']][1]}'></i>{badge[v['status']][0]}</span></td>"
        f"<td>{FRIENDLY_DATE(v['last_new_data'])}</td><td>{html.escape(str(v['data_through'] or '—'))}</td>"
        f"<td>{FRIENDLY_DATE(v['last_checked'])}</td><td>{html.escape(v['check'])}</td><td>{FRIENDLY_DATE(v['added'])}</td></tr>"
        for k, v in rows)
    sm = meta["summary"]
    return (f'<article class="prose wide"><h1>Data status</h1>'
            f"<p>{sm['sources']} sources are checked on a schedule; when one publishes new data, the site rebuilds and republishes. "
            f"Last build: {meta['built'][:16].replace('T', ' ')} UTC. "
            f"{len(sm['updated_last_7_days'])} sources brought new data in the past 7 days; "
            f"{len(sm['added_last_30_days'])} were added in the past 30 days. "
            f"A source is marked late when it goes longer than expected without new data.</p>"
            f"<table><thead><tr><th>Source</th><th>Status</th><th>Last new data</th><th>Data through</th><th>Last checked</th>"
            f"<th>Checked</th><th>Added</th></tr></thead><tbody>{trs}</tbody></table>"
            + analysis_section()
            + claims_section(nar)
            + quality_section()
            + f"<p>Hand-entered references (PJM capacity auction results, market monitor findings, curated utility tables) are updated "
            f'when published; see <a href="methods.html">Methods</a>.</p></article>')


def footer(meta: dict, price_through: str, page: str = "Other") -> str:
    s = meta["sources"]
    run = ROOT / "analysis" / "results" / "run.json"
    auctions = json.loads(run.read_text())["capacity_auctions_through"] if run.exists() else "the latest auction"
    fresh = lambda k: s.get(k, {}).get("last_new_data") or "—"
    return (status_line(meta) + f"<span>Updated automatically when sources publish new data. Last build {meta['built'][:10]}. "
            f"Residential prices through {price_through}; data center sites as of {fresh('fractracker_datacenters')}; "
            f"PJM auctions through {auctions}.</span>"
            f"<span>Data: EIA, PJM, PJM Independent Market Monitor, BLS, NOAA, Census, ORNL; data center locations from "
            f"FracTracker Alliance (non-commercial use), PNNL IM3, © OpenStreetMap contributors, PeeringDB. "
            f'<a href="methods.html">Methods and licenses</a> · <a href="{REPO}">Source code</a> · '
            f'<a href="{html.escape(build_findings.feedback_url(page))}">Report an issue</a></span>')


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
    foot = footer(meta, pm, "Findings")

    # Findings
    nar = build_findings.load_narrative()
    title, t = split_template((TEMPLATES / "findings.html.tmpl").read_text())
    t = build_findings.render(t.replace("__DATA__", json.dumps(build_findings.payload(), separators=(",", ":"))), nar)
    t = t.replace("Grid Impact Tracker · findings draft", "Grid Impact Tracker · findings")
    t = t.replace("Draft built", "Built")
    (DIST / "findings.html").write_text(shell("findings.html", title, t, foot,
        "How US data center growth is affecting residential electricity bills, from utility data 2015 to present."))

    # Map (MapLibre; tract and county layers load from data/*.json at runtime)
    sites = json.loads((DATA / "sites_open.json").read_text()) + json.loads((DATA / "sites_fractracker.json").read_text())
    title, t = split_template((TEMPLATES / "map.html.tmpl").read_text())
    t = t.replace("__SITES__", json.dumps(sites, separators=(",", ":")))
    t = t.replace("https://github.com/yottachem/grid-impact/issues/new?template=data-correction.yml", html.escape(build_findings.feedback_url("Map")))
    (DIST / "index.html").write_text(shell("index.html", title, t, footer(meta, pm, "Map"),
        "Zoomable map of US data centers with neighborhood electricity costs and county data center load per household."))
    # Old links to map.html land on the map (now the home page)
    (DIST / "map.html").write_text('<!doctype html><meta charset="utf-8"><title>Data Center Map</title>'
                                   '<meta http-equiv="refresh" content="0; url=./"><link rel="canonical" href="./">'
                                   '<p><a href="./">Go to the map</a></p>')

    # Your utility
    title, t = split_template((TEMPLATES / "utility.html.tmpl").read_text())
    t = (t.replace("__USAGE__", (DATA / "utility_usage_bill.json").read_text())
          .replace("__EXPOSURE__", (DATA / "utility_exposure.json").read_text())
          .replace("__CAPACITY__", (DATA / "capacity_household_cost.json").read_text())
          .replace("__CROWD__", (DATA / "crowd.json").read_text())
          .replace("__RELIABILITY__", (DATA / "utility_reliability.json").read_text())
          .replace("__REALMONTH__", html.escape(meta.get("real_dollars_of", "the latest CPI month"))))
    (DIST / "utility.html").write_text(shell("utility.html", title, t, footer(meta, pm, "Your utility"),
        "Residential price, usage, and bill by utility, adjusted for inflation, with data center load in each territory."))

    # Methods (methods.md + data licenses)
    md = methods_markdown(nar)
    md = re.sub(r"\*Records each modeling decision.*?\*\n", "", md)
    md += "\n\n## Data downloads and licenses\n\n" + (DATA / "README.md").read_text().split("\n", 2)[2].replace("](", "](data/")
    md += "\n\nFiles: " + ", ".join(f"[{f.name}](data/{f.name})" for f in sorted(DATA.glob("*.json"))) + "\n"
    body = '<article class="prose">' + markdown.markdown(md, extensions=["tables"]) + "</article>"
    (DIST / "methods.html").write_text(shell("methods.html", "Methods", body, footer(meta, pm, "Methods"),
        "Sources, modeling decisions, and known limitations of the Grid Impact Tracker."))
    (DIST / "status.html").write_text(shell("status.html", "Data status", status_page(meta, nar), footer(meta, pm, "Data status"),
        "When each data source was added, last checked, and last brought new data."))
    shutil.copytree(DATA / "tracts", DIST / "data" / "tracts")
    (DIST / ".nojekyll").write_text("")
    for f in sorted(DIST.glob("*.html")):
        print(f"wrote site/dist/{f.name}  {f.stat().st_size / 1024:,.0f} KB")


if __name__ == "__main__":
    main()
