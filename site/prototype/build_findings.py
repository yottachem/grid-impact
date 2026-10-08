"""Build the findings page from site/data exports and analysis/results.

All wording comes from analysis/results/narrative.json (written by analysis/narrative.py from
analysis/claims.yaml); the template only holds layout and {{claim:id}} / {{figure:id}} slots.
The chart data travels to the page as JSON for the D3 charts.
Usage: uv run python site/prototype/build_findings.py [out.html]"""
import html
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT))
from analysis import narrative  # noqa: E402
sys.path.insert(0, str(HERE.parent))
import references  # noqa: E402  (site/references.py)

DATA = HERE.parent / "data"
RESULTS = ROOT / "analysis" / "results"
FEEDBACK_FALLBACK = "https://github.com/yottachem/grid-impact/issues/new?template=data-correction.yml"


def load_narrative() -> dict:
    """The claims as checked by the latest analysis run (re-checked here if the file is missing)."""
    p = RESULTS / "narrative.json"
    return json.loads(p.read_text()) if p.exists() else narrative.evaluate()


def payload() -> dict:
    """Data for the charts (wording is rendered server-side from the narrative)."""
    cases, ytd = narrative.case_series()
    meta = json.loads((DATA / "meta.json").read_text())
    run = json.loads((RESULTS / "run.json").read_text()) if (RESULTS / "run.json").exists() else {}
    es = json.loads((DATA / "event_studies.json").read_text())["pjm_vs_rest"]
    any_ytd = next(iter(ytd.values()))
    return {"capacity": narrative.capacity_series(), "capacity_ne": narrative.capacity_series("ISONE"), "capacity_miso": narrative.capacity_series("MISO"), "event_pjm": es, "cases": cases, "run": run,
            "ytd_year": any_ytd["year"], "ytd_months": any_ytd["months"].replace("-", "–"),
            "built": meta["built"][:10], "price_through": meta["sources"]["eia861m"]["last_new_data"] or ""}


def feedback_url(page: str) -> str:
    """Prefilled 'Report an issue' form link for a page (GitHub issue form until the form exists)."""
    p = DATA / "crowd.json"
    fb = (json.loads(p.read_text()).get("feedback") or {}) if p.exists() else {}
    if fb.get("form_url") and fb.get("page_entry"):
        from urllib.parse import quote
        return f"{fb['form_url']}?usp=pp_url&entry.{fb['page_entry']}={quote(page)}"
    return fb.get("form_url") or FEEDBACK_FALLBACK


def claim_html(c: dict, numbering: dict | None = None, pub: dict | None = None) -> str:
    if not c["html"]:
        return ""
    body = references.footnotes(c["html"], c.get("refs") or [], numbering, pub) if pub is not None else c["html"]
    if c["status"] == "ok":
        return body
    label = "data under review" if c["status"] == "data_check" else "under review"
    return f'{body} <span class="review" title="{html.escape(c["reason"] or "")}">{label}</span>'


def render(t: str, nar: dict) -> str:
    claims = nar["claims"]
    pub, numbering = references.approved(), {}
    t = re.sub(r"\{\{claim:([a-z0-9_]+)\}\}", lambda m: claim_html(claims[m.group(1)], numbering, pub), t)
    t = re.sub(r"\{\{plain:([a-z0-9_]+)\}\}", lambda m: claims[m.group(1)]["html"], t)  # no badge (headline; the banner covers it)
    t = re.sub(r"\{\{figure:([a-z0-9_]+)\}\}", lambda m: (
        f'<div class="fig"><span class="fig-n">{html.escape(claims[m.group(1)]["value"])}</span>'
        f'<span class="fig-l">{claim_html(claims[m.group(1)])}</span></div>'), t)
    flagged = [c for c in nar["flagged"] if claims[c]["where"] == "findings"]
    banner = ""
    if flagged:
        banner = (f'<p class="banner" role="status"><b>Some findings are under review.</b> Data updated '
                  f'{narrative.fmt(nar["run_date"], "date")} no longer fits the earlier wording of {len(flagged)} '
                  f'statement{"s" if len(flagged) > 1 else ""} on this page. They show current figures without interpretation '
                  f'until reviewed.</p>')
    return (t.replace("{{review_banner}}", banner)
             .replace("{{feedback_url}}", html.escape(feedback_url("Findings"))))


def main(out: str = "findings.html") -> None:
    data = payload()
    t = (HERE.parent / "templates" / "findings.html.tmpl").read_text().replace("__DATA__", json.dumps(data, separators=(",", ":")))
    t = render(t, load_narrative())
    Path(out).write_text(t)
    print(f"wrote {out} ({len(t) / 1e3:.0f} KB)")


if __name__ == "__main__":
    main(*sys.argv[1:])
