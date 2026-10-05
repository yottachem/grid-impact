"""Run every source due at a given check cadence. Exit code 0 always; writes
data/raw/_changed.txt listing sources with new data so CI can decide whether to rebuild."""
import argparse
import importlib
import traceback

from ingest.common import RAW, load_sources

ORDER = {"daily": ["daily"], "weekly": ["daily", "weekly"], "all": ["daily", "weekly", "monthly"]}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cadence", choices=ORDER, default="all")
    ap.add_argument("--only", nargs="*", help="source ids to run")
    args = ap.parse_args()

    changed, failed = [], []
    for sid, cfg in load_sources().items():
        if args.only and sid not in args.only:
            continue
        if not args.only and cfg["check"] not in ORDER[args.cadence]:
            continue
        try:
            if importlib.import_module(cfg["module"]).run():
                changed.append(sid)
            print(f"ok      {sid}{'  (new data)' if sid in changed else ''}")
        except Exception:
            failed.append(sid)
            print(f"FAILED  {sid}")
            traceback.print_exc()
    RAW.mkdir(parents=True, exist_ok=True)
    (RAW / "_changed.txt").write_text("\n".join(changed))
    if failed:
        raise SystemExit(f"failed: {', '.join(failed)}")


if __name__ == "__main__":
    main()
