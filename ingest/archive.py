"""Durable archive of raw snapshots as GitHub Release assets.

The Actions cache that carries data/raw between runs is temporary (evicted after 7 days
unused, 10 GB per repo). This packs every snapshot file not yet archived into
raw-<UTC timestamp>.tar.gz and attaches it to the month's release (tag raw-YYYY-MM),
creating the release if needed. data/raw/_archived.txt (carried in the cache) lists
archived files; if the cache is lost, the next run archives everything again, which
duplicates files but loses nothing. Restore: download every
asset from the raw-* releases and extract them in order into data/raw.

Usage (CI): python -m ingest.archive"""
import os
import subprocess
import tarfile
from datetime import datetime, timezone
from pathlib import Path

from ingest.common import RAW, ROOT

REPO = os.environ.get("GITHUB_REPOSITORY", "yottachem/grid-impact")
LEDGER = RAW / "_archived.txt"


def gh(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["gh", *args, "-R", REPO], capture_output=True, text=True, check=check)


def snapshot_files() -> list[Path]:
    """Dated snapshot files and manifests (not the ledger or run markers)."""
    out = []
    for p in sorted(RAW.rglob("*")):
        if p.is_file() and not p.name.startswith("_") and (p.name == "manifest.jsonl" or p.parent.name[:2] == "20"):
            out.append(p)
    return out


def main() -> None:
    done = set(LEDGER.read_text().splitlines()) if LEDGER.exists() else set()
    # Manifests change every run; archive them each time. Data files only once.
    todo = [p for p in snapshot_files() if p.name == "manifest.jsonl" or str(p.relative_to(RAW)) not in done]
    data_files = [p for p in todo if p.name != "manifest.jsonl"]
    if not data_files:
        print("archive: no new snapshot files")
        return
    now = datetime.now(timezone.utc)
    tag, name = f"raw-{now:%Y-%m}", ROOT / f"raw-{now:%Y%m%dT%H%M%SZ}.tar.gz"
    with tarfile.open(name, "w:gz") as tar:
        for p in todo:
            tar.add(p, arcname=str(p.relative_to(RAW)))
    if gh("release", "view", tag, check=False).returncode != 0:
        gh("release", "create", tag, "--title", f"Raw source snapshots {now:%B %Y}",
           "--notes", "Immutable dated snapshots of every source, appended as each scheduled run finds new data. "
                      "Extract all assets in order into data/raw to restore. See ingest/archive.py.")
    gh("release", "upload", tag, str(name))
    with LEDGER.open("a") as f:
        for p in data_files:
            f.write(str(p.relative_to(RAW)) + "\n")
    print(f"archive: {len(data_files)} new files ({name.stat().st_size / 1e6:,.1f} MB) -> release {tag}")
    name.unlink()


if __name__ == "__main__":
    main()
