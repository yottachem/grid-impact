"""GitHub issues for things that need a person: findings statements under review, plausibility
checks that failed, hand-entered facts past their review date, and new site feedback.

Runs in CI after the analysis and site build (needs GH_TOKEN). Idempotent: one open issue per
statement; an issue closes itself with a comment once its statement fits the data again.
Issues are public, so they carry only the statement, its condition, and current figures.
Feedback issues carry only a count; the reports stay in the private Google Sheet.

Usage: uv run python -m analysis.claim_issues [--dry-run]"""
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NARRATIVE = ROOT / "analysis" / "results" / "narrative.json"
CROWD = ROOT / "site" / "data" / "crowd.json"
LABELS = {
    "findings-review": ("d95926", "A findings statement no longer fits the data"),
    "data-check": ("eda100", "A figure failed its plausibility check"),
    "facts-review": ("2a78d6", "A hand-entered fact is past its review date"),
    "site-feedback": ("1baf7a", "New reports from the site's Report an issue form"),
}
DRY = "--dry-run" in sys.argv


def gh(*args: str, write: bool = False) -> str:
    if write and DRY:
        print("[dry-run] gh", " ".join(a if len(a) < 80 else a[:77] + "..." for a in args))
        return ""
    return subprocess.run(["gh", *args], check=True, capture_output=True, text=True).stdout


def open_issues(label: str) -> list[dict]:
    return json.loads(gh("issue", "list", "--label", label, "--state", "open", "--json", "number,title,body", "--limit", "200") or "[]")


def ensure_labels() -> None:
    for name, (color, desc) in LABELS.items():
        gh("label", "create", name, "--color", color, "--description", desc, "--force", write=True)


def fmt_value(x) -> str:
    return f"{x:,.3f}".rstrip("0").rstrip(".") if isinstance(x, float) else str(x)


def claim_body(cid: str, c: dict, nar: dict) -> str:
    rows = "\n".join(f"| `{k}` | {fmt_value(x)} |" for k, x in c["values"].items())
    approved = (f"**Approved wording, filled with current numbers** (no longer supported):\n\n> {c['approved_text']}\n\n"
                if c.get("approved_text") else "")
    fix = ("If the figure is real, widen its range under `checks:` in `analysis/claims.yaml` and review the wording. "
           "If not, trace it to the source data." if c["status"] == "data_check" else
           "In Claude Code, from the grid-impact repo, run `/rewrite-claims`. It drafts new wording and a matching "
           "condition in `analysis/claims.yaml` for your review; nothing is published until you approve and merge it.")
    return (f"Statement `{cid}` on the **{c['where']}** page no longer fits the data.\n\n"
            f"**Why:** {c['reason']}\n\n{approved}"
            f"**Shown on the site now** (current figures, marked under review):\n\n> {c['text'] or '(hidden)'}\n\n"
            f"| Value | Current |\n|---|---|\n{rows}\n\n"
            f"Analysis run {nar['run_date']}, residential prices through {nar['prices_through']}.\n\n"
            f"### To resolve\n{fix}\n\n<!-- claim:{cid} -->")


def sync_claims(nar: dict) -> None:
    flagged = {cid: nar["claims"][cid] for cid in nar["flagged"]}
    existing = {}
    for label in ("findings-review", "data-check"):
        for i in open_issues(label):
            m = re.search(r"<!-- claim:([a-z0-9_]+) -->", i["body"] or "")
            if m:
                existing[m.group(1)] = i
    for cid, c in flagged.items():
        if cid in existing:
            continue
        label = "data-check" if c["status"] == "data_check" else "findings-review"
        kind = "Data check" if label == "data-check" else "Findings review"
        gh("issue", "create", "--title", f"{kind}: {cid}", "--label", label, "--body", claim_body(cid, c, nar), write=True)
        print(f"opened issue for {cid} ({label})")
    for cid, i in existing.items():
        if cid not in flagged:
            gh("issue", "close", str(i["number"]), "--comment",
               f"`{cid}` fits the data again (analysis run {nar['run_date']}, prices through {nar['prices_through']}). Closing.", write=True)
            print(f"closed issue #{i['number']} ({cid})")


def sync_facts(nar: dict) -> None:
    due = nar.get("facts_due") or []
    issues = open_issues("facts-review")
    if due and not issues:
        rows = "\n".join(f"| `{f['fact']}` | {f['statement']} | {f['review_by']} | {f['source']} |" for f in due)
        gh("issue", "create", "--title", "Reference facts due for review", "--label", "facts-review", "--body",
           "These hand-entered facts in `reference/context_facts.csv` are past their review date. Check each against its "
           "source; update `value`, `statement`, `as_of`, and `review_by`.\n\n| Fact | Statement | Review by | Source |\n"
           f"|---|---|---|---|\n{rows}", write=True)
        print(f"opened facts-review issue ({len(due)} facts)")
    elif not due:
        for i in issues:
            gh("issue", "close", str(i["number"]), "--comment", "All reference facts are within their review dates. Closing.", write=True)


def sync_feedback() -> None:
    fb = (json.loads(CROWD.read_text()).get("feedback") or {}) if CROWD.exists() else {}
    total = fb.get("total")
    if total is None:
        return
    issues = open_issues("site-feedback")
    seen = 0
    if issues:
        m = re.search(r"<!-- count:(\d+) -->", issues[0]["body"] or "")
        seen = int(m.group(1)) if m else 0
    if total <= seen:
        return
    new = total - seen
    body = (f"The site's **Report an issue** form has {total} report{'s' if total != 1 else ''} in total. Read them in the "
            f"**Feedback (private)** tab of the Grid Impact Google Sheet (automate617@gmail.com). Report text is never "
            f"copied here because this repository is public.\n\nThis issue gets a comment whenever new reports arrive; close "
            f"it after reading and a new one opens with the next report.\n\n<!-- count:{total} -->")
    if issues:
        gh("issue", "comment", str(issues[0]["number"]), "--body", f"{new} new report{'s' if new != 1 else ''} ({total} total).", write=True)
        gh("issue", "edit", str(issues[0]["number"]), "--body", body, write=True)
    else:
        # A closed issue's count carries over so old reports are not announced again
        closed = json.loads(gh("issue", "list", "--label", "site-feedback", "--state", "closed", "--json", "body", "--limit", "1") or "[]")
        m = re.search(r"<!-- count:(\d+) -->", closed[0]["body"] or "") if closed else None
        if m and int(m.group(1)) >= total:
            return
        new = total - (int(m.group(1)) if m else 0)
        gh("issue", "create", "--title", "Site feedback", "--label", "site-feedback", "--body",
           f"{new} new report{'s' if new != 1 else ''}.\n\n" + body, write=True)
    print(f"site feedback: {new} new ({total} total)")


def main() -> None:
    nar = json.loads(NARRATIVE.read_text())
    ensure_labels()
    sync_claims(nar)
    sync_facts(nar)
    sync_feedback()


if __name__ == "__main__":
    main()
