"""References page and citation helpers, from reference/literature.yaml.

Only approved entries are published. Each entry lists what it cites (one level down), what cites it,
and where this site uses it: Findings and Methods statements (analysis/claims.yaml `refs:`) and
hand-entered facts (reference/context_facts.csv `ref`)."""
import html
from datetime import date
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parent.parent
LIT = ROOT / "reference" / "literature.yaml"
TYPE_LABEL = {"peer-reviewed": "Peer-reviewed", "government": "Government", "grid-operator": "Grid operator",
              "market-monitor": "Market monitor", "regulator": "Regulator", "research-org": "Research", "industry": "Industry",
              "advocacy": "Advocacy", "news": "News", "dataset": "Dataset"}
RELATION_LABEL = {"supports": "Consistent with our findings", "differs": "Differs from our findings",
                  "mixed": "Partly consistent", "context": "Background"}
CSS = """
.refs { max-width: 980px; margin: 0 auto; padding-inline: 20px; padding-block: 28px 48px; display: grid; gap: 20px; }
.refs h1 { font: 600 38px/1.05 var(--font-display); margin: 0; }
.refs .lede { margin: 0; color: var(--muted); max-width: 72ch; }
.refs h2 { font: 600 24px/1.15 var(--font-display); margin: 12px 0 0; }
.filters { display: flex; flex-wrap: wrap; gap: 6px 8px; align-items: center; font-size: 13px; }
.filters .k { color: var(--muted); margin-right: 4px; font: 500 11px/1 var(--font-data); text-transform: uppercase; letter-spacing: .06em; }
.chip { border: 1px solid var(--line); background: var(--surface); color: var(--fg); border-radius: 999px; padding: 4px 10px; font: inherit; cursor: pointer; }
.chip[aria-pressed="true"] { border-color: var(--s1); color: var(--s1); }
.ref { background: var(--surface); border: 1px solid var(--line); border-radius: 8px; padding: 14px 16px; display: grid; gap: 6px; min-width: 0; scroll-margin-top: 70px; }
.ref:target { border-color: var(--s1); box-shadow: 0 0 0 2px var(--s1); }
.ref h3 { font: 600 17px/1.3 var(--font-body); margin: 0; text-wrap: balance; }
.ref h3 a { color: var(--fg); }
.ref .cite { font-size: 13px; color: var(--muted); }
.ref .tags { display: flex; flex-wrap: wrap; gap: 6px; }
.tag { font: 500 11px/1.6 var(--font-data); letter-spacing: .04em; text-transform: uppercase; border-radius: 4px; padding: 0 6px; border: 1px solid var(--line); color: var(--muted); }
.tag.rel-supports { color: var(--s3); border-color: currentColor; }
.tag.rel-differs { color: var(--s2); border-color: currentColor; }
.tag.rel-mixed { color: var(--s4); border-color: currentColor; }
.ref ul { margin: 2px 0; padding-left: 20px; } .ref li { max-width: 80ch; }
.ref p { margin: 0; max-width: 80ch; }
.ref .meta { font-size: 13px; color: var(--muted); }
.ref .meta a { color: var(--s1); }
.count { font-size: 13px; color: var(--muted); }
"""
JS = """
const state = { topic: "all", type: "all" };
function apply() {
  let n = 0;
  document.querySelectorAll(".ref").forEach(el => {
    const ok = (state.topic === "all" || el.dataset.topics.split(" ").includes(state.topic)) &&
               (state.type === "all" || el.dataset.type === state.type);
    el.hidden = !ok; if (ok) n++;
  });
  document.querySelectorAll("section.group").forEach(g => { g.hidden = !g.querySelector(".ref:not([hidden])"); });
  document.getElementById("count").textContent = `${n} shown`;
}
document.querySelectorAll(".chip").forEach(b => b.addEventListener("click", () => {
  state[b.dataset.k] = b.dataset.v;
  document.querySelectorAll(`.chip[data-k="${b.dataset.k}"]`).forEach(c => c.setAttribute("aria-pressed", String(c === b)));
  apply();
}));
apply();
"""


def load() -> dict:
    return yaml.safe_load(LIT.read_text())


def approved(lit: dict | None = None) -> dict:
    """Published entries by id, in the order they appear in the file."""
    lit = lit or load()
    return {e["id"]: e for e in lit.get("entries") or [] if e.get("approved")}


def short(e: dict) -> str:
    """Short citation label: 'EPRI, 2026'."""
    who = e.get("authors") or [e.get("publisher", "")]
    who = who[0].split(",")[0] + (" et al." if len(who) > 2 else f" and {who[1].split(',')[0]}" if len(who) == 2 else "")
    return f"{who}, {str(e.get('date', ''))[:4]}"


def citation(e: dict) -> str:
    authors = "; ".join(e.get("authors") or [])
    parts = [p for p in (authors, e.get("publisher") if e.get("publisher") not in (authors,) else None, fmt_date(e.get("date"))) if p]
    return ". ".join(parts)


def fmt_date(d) -> str:
    s = str(d or "")
    try:
        if len(s) == 7:
            return pd.Timestamp(s + "-01").strftime("%B %Y")
        if len(s) == 10:
            t = pd.Timestamp(s)
            return f"{t:%B} {t.day}, {t.year}"
    except ValueError:
        pass
    return s


def usage(nar: dict) -> dict[str, list[str]]:
    """Where each reference is used on the site: statements (by page) and hand-entered facts."""
    out: dict[str, list[str]] = {}
    labels = {"findings": ("Findings", "findings.html"), "methods": ("Methods", "methods.html")}
    for cid, c in nar["claims"].items():
        for r in c.get("refs") or []:
            name, href = labels.get(c["where"], (c["where"].title(), "#"))
            link = f'<a href="{href}">{name}</a>'
            if link not in out.setdefault(r, []):
                out[r].append(link)
    facts = pd.read_csv(ROOT / "reference" / "context_facts.csv", dtype=str)
    if "ref" in facts:
        for r in facts.dropna(subset=["ref"]).itertuples():
            for ref in str(r.ref).split(";"):
                out.setdefault(ref.strip(), []).append(f'fact <code>{html.escape(r.fact_id)}</code> (<a href="status.html">Data status</a>)')
    return out


def entry_html(e: dict, pub: dict, cited_by: dict, used: dict) -> str:
    esc = html.escape
    url = e.get("url") or (f"https://doi.org/{e['doi']}" if e.get("doi") else "")
    title = f'<a href="{esc(url)}">{esc(e["title"])}</a>' if url else esc(e["title"])
    tags = [f'<span class="tag">{esc(TYPE_LABEL.get(e["type"], e["type"]))}</span>']
    rel = e.get("relation", "context")
    if rel != "context":
        tags.append(f'<span class="tag rel-{rel}">{esc(RELATION_LABEL[rel])}</span>')
    findings = "".join(f"<li>{esc(f)}</li>" for f in e.get("findings") or [])
    link = lambda i: f'<a href="#{esc(i)}">{esc(pub[i]["title"])}</a> ({esc(short(pub[i]))})'
    meta = []
    if e.get("relation_note"):
        meta.append(f"<b>Compared with this site:</b> {esc(e['relation_note'])}")
    cites = [i for i in e.get("cites") or [] if i in pub]
    if cites:
        meta.append("<b>Draws on:</b> " + "; ".join(link(i) for i in cites))
    if cited_by.get(e["id"]):
        meta.append("<b>Cited by:</b> " + "; ".join(link(i) for i in cited_by[e["id"]]))
    if used.get(e["id"]):
        meta.append("<b>Used on this site:</b> " + "; ".join(used[e["id"]]))
    if e.get("accessed"):
        meta.append(f"Accessed {esc(fmt_date(e['accessed']))}")
    return (f'<article class="ref" id="{esc(e["id"])}" data-type="{esc(e["type"])}" data-topics="{esc(" ".join(e.get("topics") or []))}">'
            f'<h3>{title}</h3><div class="cite">{esc(citation(e))}</div><div class="tags">{"".join(tags)}</div>'
            f'<p>{esc(e.get("summary", ""))}</p>' + (f"<ul>{findings}</ul>" if findings else "")
            + "".join(f'<p class="meta">{m}</p>' for m in meta) + "</article>")


def page(nar: dict) -> str:
    lit = load()
    pub = approved(lit)
    topics = lit["topics"]
    cited_by: dict[str, list[str]] = {}
    for e in pub.values():
        for c in e.get("cites") or []:
            cited_by.setdefault(c, []).append(e["id"])
    used = usage(nar)
    # Group by each entry's first topic; newest first within a group
    groups = {k: [] for k in topics}
    for e in sorted(pub.values(), key=lambda e: str(e.get("date", "")), reverse=True):
        groups[(e.get("topics") or ["load-growth"])[0]].append(e)
    types = sorted({e["type"] for e in pub.values()}, key=lambda t: list(TYPE_LABEL).index(t))
    chip = lambda k, v, label, on=False: f'<button class="chip" data-k="{k}" data-v="{v}" aria-pressed="{str(on).lower()}">{html.escape(label)}</button>'
    filters = (f'<div class="filters"><span class="k">Topic</span>{chip("topic", "all", "All", True)}'
               + "".join(chip("topic", k, v) for k, v in topics.items() if any(k in (e.get("topics") or []) for e in pub.values()))
               + f'</div><div class="filters"><span class="k">Type</span>{chip("type", "all", "All", True)}'
               + "".join(chip("type", t, TYPE_LABEL[t]) for t in types) + '</div><div class="count" id="count"></div>')
    body = "".join(f'<section class="group" data-topic="{k}"><h2>{html.escape(topics[k])}</h2><div style="display:grid;gap:10px">'
                   + "".join(entry_html(e, pub, cited_by, used) for e in es) + "</div></section>"
                   for k, es in groups.items() if es)
    if not pub:
        body = "<p>The first set of references is being reviewed.</p>"
    return (f"<style>{CSS}</style><div class=\"refs\"><h1>References</h1>"
            f"<p class=\"lede\">Research, regulatory filings, market reports, and news on data centers, the grid, and household "
            f"electricity costs: {len(pub)} items. Each lists what it draws on and how it compares with this site's findings, "
            f"including where it differs. Items marked as used here are cited from the Findings and Methods pages. "
            f"Summaries are ours; follow the links for the originals. Know of something missing? "
            f"<a href=\"__FEEDBACK__\">Suggest a reference</a>.</p>{filters}{body}</div><script>{JS}</script>")


def footnotes(text_html: str, ids: list[str], numbering: dict, pub: dict) -> str:
    """Append numbered citation links for approved references (numbering shared across a page)."""
    marks = []
    for i in ids:
        if i not in pub:
            continue
        n = numbering.setdefault(i, len(numbering) + 1)
        marks.append(f'<a href="references.html#{html.escape(i)}" title="{html.escape(short(pub[i]) + ": " + pub[i]["title"])}">{n}</a>')
    return text_html + (f'<sup class="fn">{",".join(marks)}</sup>' if marks else "")


def check() -> list[str]:
    """Problems in literature.yaml (used by tests)."""
    lit = load()
    problems, ids = [], set()
    for e in lit.get("entries") or []:
        for f in ("id", "title", "type", "topics", "summary", "relation", "use", "date"):
            if not e.get(f):
                problems.append(f"{e.get('id', '?')}: missing {f}")
        if e.get("id") in ids:
            problems.append(f"duplicate id {e['id']}")
        ids.add(e.get("id"))
        if e.get("type") not in TYPE_LABEL:
            problems.append(f"{e.get('id')}: unknown type {e.get('type')}")
        if e.get("relation") not in RELATION_LABEL:
            problems.append(f"{e.get('id')}: unknown relation {e.get('relation')}")
        for t in e.get("topics") or []:
            if t not in lit["topics"]:
                problems.append(f"{e.get('id')}: unknown topic {t}")
        if not (e.get("url") or e.get("doi")):
            problems.append(f"{e.get('id')}: no url or doi")
    for e in lit.get("entries") or []:
        for c in e.get("cites") or []:
            if c not in ids:
                problems.append(f"{e['id']}: cites unknown {c}")
    return problems


def due(today: str | None = None) -> list[dict]:
    today = today or date.today().isoformat()
    return [e for e in approved().values() if e.get("review_by") and str(e["review_by"]) <= today]


if __name__ == "__main__":
    print("\n".join(check()) or "literature.yaml ok")
    lit = load()
    print(f"{len(lit.get('entries') or [])} entries, {len(approved(lit))} approved")
