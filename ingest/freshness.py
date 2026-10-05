"""Freshness monitor: flag sources whose last *changed* snapshot is older than
expected_max_gap_days. Exit 1 (CI opens an issue) when any source is stale."""
import json
from datetime import datetime, timezone

from ingest.common import RAW, load_sources


def stale_sources() -> list[str]:
    now = datetime.now(timezone.utc)
    out = []
    for sid, cfg in load_sources().items():
        m = RAW / sid / "manifest.jsonl"
        entries = [json.loads(l) for l in m.read_text().splitlines()] if m.exists() else []
        changed = [e for e in entries if e.get("changed")]
        if not changed:
            out.append(f"{sid}: never fetched")
            continue
        age = (now - datetime.fromisoformat(changed[-1]["checked_at"])).days
        if age > cfg["expected_max_gap_days"]:
            out.append(f"{sid}: no new data in {age} days (expected <= {cfg['expected_max_gap_days']})")
    return out


if __name__ == "__main__":
    stale = stale_sources()
    print("\n".join(stale) or "all sources fresh")
    raise SystemExit(1 if stale else 0)
