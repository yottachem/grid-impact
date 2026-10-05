"""Run every source due at a given check cadence. Writes data/raw/_changed.txt listing
sources with new data so CI can decide whether to rebuild.

Transient upstream problems (timeouts, 429, 5xx) are warnings: the source is retried on
its next schedule and the freshness monitor alerts if it stays down. Anything else
(parse errors, auth failures, changed formats) fails the run."""
import argparse
import importlib
import traceback

import requests

from ingest.common import RAW, load_sources

ORDER = {"daily": ["daily"], "weekly": ["daily", "weekly"], "all": ["daily", "weekly", "monthly"]}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cadence", choices=ORDER, default="all")
    ap.add_argument("--only", nargs="*", help="source ids to run")
    args = ap.parse_args()

    changed, failed, transient = [], [], []
    for sid, cfg in load_sources().items():
        if args.only and sid not in args.only:
            continue
        if not args.only and cfg["check"] not in ORDER[args.cadence]:
            continue
        try:
            if importlib.import_module(cfg["module"]).run():
                changed.append(sid)
            print(f"ok      {sid}{'  (new data)' if sid in changed else ''}")
        except Exception as e:
            if _is_transient(e):
                transient.append(sid)
                print(f"WARN    {sid}  upstream unavailable, will retry next run: {e}")
            else:
                failed.append(sid)
                print(f"FAILED  {sid}")
                traceback.print_exc()
    RAW.mkdir(parents=True, exist_ok=True)
    (RAW / "_changed.txt").write_text("\n".join(changed))
    if failed:
        raise SystemExit(f"failed: {', '.join(failed)}")


def _is_transient(e: Exception) -> bool:
    if isinstance(e, (requests.ConnectionError, requests.Timeout)):
        return True
    if isinstance(e, requests.HTTPError) and e.response is not None:
        return e.response.status_code == 429 or e.response.status_code >= 500
    return False


if __name__ == "__main__":
    main()
