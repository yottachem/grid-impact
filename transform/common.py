"""Paths and helpers shared by transforms. Transforms read the latest raw snapshot of each
source and write staged/ (cleaned, one table per source) and marts/ (analysis-ready)."""
import glob
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW, STAGED, MARTS = (ROOT / "data" / d for d in ("raw", "staged", "marts"))


def latest(source_id: str, pattern: str) -> str:
    """Path of the most recent snapshot of `pattern` for a source (snapshots are only
    written on change, so the newest dated folder holding the file is current)."""
    hits = sorted(glob.glob(str(RAW / source_id / "*" / pattern)))
    if not hits:
        raise FileNotFoundError(f"no snapshot of {source_id}/{pattern}; run ingest first")
    return hits[-1]


def snapshot_date(path: str) -> str:
    return Path(path).parent.name


def write(df: pd.DataFrame, layer: Path, name: str) -> Path:
    layer.mkdir(parents=True, exist_ok=True)
    out = layer / f"{name}.parquet"
    df.to_parquet(out, index=False)
    print(f"wrote {out.relative_to(ROOT)}  rows={len(df):,}")
    return out
