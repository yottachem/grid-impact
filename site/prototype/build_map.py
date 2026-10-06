"""Build the data center map page from site/data exports (prototype for the public site).
Usage: uv run python site/prototype/build_map.py [out.html]
Includes FracTracker-derived sites, so the output is for private review or must carry
FracTracker's non-commercial terms if shared."""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE.parent / "data"


def main(out: str = "us-data-center-buildout.html") -> None:
    sites = json.loads((DATA / "sites_open.json").read_text()) + json.loads((DATA / "sites_fractracker.json").read_text())
    t = (HERE.parent / "templates" / "map.html.tmpl").read_text()
    t = (t.replace("__SITES__", json.dumps(sites, separators=(",", ":")))
          .replace("__COUNTIES__", (DATA / "counties.json").read_text())
          .replace("__TOPO__", (HERE.parent / "templates" / "counties-10m.json").read_text())
          .replace("__META__", (DATA / "meta.json").read_text()))
    Path(out).write_text(t)
    print(f"wrote {out} ({len(t) / 1e6:.2f} MB, {len(sites):,} sites)")


if __name__ == "__main__":
    main(*sys.argv[1:])
