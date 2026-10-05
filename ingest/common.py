"""Shared fetch/snapshot helpers. Every source writes immutable, dated raw snapshots
and appends to a per-source manifest; unchanged content is not re-written."""
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
import yaml

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
USER_AGENT = "grid-impact/0.1 (open research; github.com/yottachem/grid-impact)"


def load_sources() -> dict:
    return yaml.safe_load((ROOT / "sources.yaml").read_text())["sources"]


def http_get(url: str, retries: int = 4, **kwargs) -> requests.Response:
    headers = {"User-Agent": USER_AGENT, **kwargs.pop("headers", {})}
    for attempt in range(retries + 1):
        r = requests.get(url, headers=headers, timeout=120, **kwargs)
        if r.status_code not in (429, 502, 503, 504) or attempt == retries:
            break
        time.sleep(int(r.headers.get("Retry-After", 0)) or 15 * 2**attempt)
    r.raise_for_status()
    return r


def _manifest(source_id: str) -> Path:
    return RAW / source_id / "manifest.jsonl"


def last_entry(source_id: str) -> dict | None:
    m = _manifest(source_id)
    if not m.exists():
        return None
    lines = m.read_text().strip().splitlines()
    return json.loads(lines[-1]) if lines else None


def snapshot(source_id: str, content: bytes, filename: str, meta: dict | None = None) -> Path | None:
    """Write content to data/raw/<source>/<UTC date>/<filename> if it differs from the
    last snapshot. Returns the path written, or None when upstream is unchanged."""
    digest = hashlib.sha256(content).hexdigest()
    now = datetime.now(timezone.utc)
    prev = last_entry(source_id)
    entry = {"checked_at": now.isoformat(timespec="seconds"), "sha256": digest, "file": filename, **(meta or {})}
    if prev and prev["sha256"] == digest and prev["file"] == filename:
        entry["changed"] = False
        path = None
    else:
        entry["changed"] = True
        path = RAW / source_id / now.strftime("%Y-%m-%d") / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        entry["path"] = str(path.relative_to(ROOT))
    _manifest(source_id).parent.mkdir(parents=True, exist_ok=True)
    with _manifest(source_id).open("a") as f:
        f.write(json.dumps(entry) + "\n")
    return path
