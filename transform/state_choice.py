"""Stage state competitive-supply statistics (ingest/state_choice.py) into one table:
state, utility_id_eia, period (month), residential customers in total and on competitive supply
(competitive suppliers plus government or municipal aggregation), and the source.

Massachusetts (DOER customer choice data) is added by hand to reference/state_choice/ because mass.gov
blocks automated downloads; DOER posts it quarterly.

Each parser checks its own totals (utilities sum to the state total where the report gives one)
and fails loudly if a layout changes."""
import glob
import re
from pathlib import Path

import pandas as pd
import pymupdf

from transform.common import RAW, ROOT, STAGED, write

NUM = re.compile(r"^-?[\d,]+(\.\d+)?%?$")


def _newest() -> dict[str, str]:
    by_name = {}
    for f in sorted(glob.glob(str(RAW / "state_choice" / "*" / "*"))):
        by_name[Path(f).name] = f
    return by_name


def _n(s) -> float:
    return float(str(s).replace(",", "").replace("%", "").strip())


# ---------------------------------------------------------------- Illinois (ICC workbooks)

def illinois(path: str) -> list[dict]:
    rows = []
    utility = "Commonwealth Edison Company" if "comed" in path.lower() else "Ameren Illinois"
    for sheet, d in pd.read_excel(path, sheet_name=None, header=None).items():
        flat = d.astype(str)
        def value(label: str):
            hit = flat.apply(lambda r: r.str.contains(label, case=False, regex=False).any(), axis=1)
            if not hit.any():
                return None
            r = d[hit].iloc[0]
            nums = [v for v in r.tolist() if isinstance(v, (int, float)) and not pd.isna(v)]
            return nums[0] if nums else None
        total, res = value("Total Number of Customers"), value("Retail Electric Supplier")
        if total is None or res is None or total < 1000:
            continue  # empty future-month sheet
        when = pd.to_datetime(sheet, errors="coerce", format="mixed")
        if pd.isna(when):
            m = re.search(r"([A-Za-z]+ \d{1,2}, \d{4})", " ".join(flat.iloc[:4, 0]))
            when = pd.to_datetime(m.group(1)) if m else None
        if when is None or pd.isna(when):
            raise ValueError(f"IL: no month for sheet {sheet} in {path}")
        rows.append({"state": "IL", "source_name": utility, "period": when.to_period("M").to_timestamp(),
                     "res_total": total, "res_competitive": res, "source": "Illinois Commerce Commission monthly switching report"})
    return rows


# ---------------------------------------------------------------- Pennsylvania (PA PUC PDF)

def pennsylvania(path: str) -> list[dict]:
    text = "".join(p.get_text() for p in pymupdf.open(path))
    m = re.search(r"AS OF ([A-Z]+ \d{4})", text)
    period = pd.to_datetime(m.group(1).title(), format="%B %Y")
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    names = pd.read_csv(ROOT / "reference" / "state_choice_utilities.csv").query("state == 'PA'").source_name.tolist()
    rows, flat = [], " ".join(lines)
    for name in names + ["Statewide Total"]:
        # name, date, total #, %, % load, residential #, %, % load, ...
        pat = re.escape(name).replace(r"\ ", r"\s+") + r"\s+\d{1,2}/\d{1,2}/\d{2}\s+([\d,]+)\s+[\d.]+\s+[\d.*]+\s+([\d,]+)\s+([\d.]+)"
        hit = re.search(pat, flat)
        if not hit:
            raise ValueError(f"PA: {name} not found in {path}")
        res, pct = _n(hit.group(2)), _n(hit.group(3))
        rows.append({"state": "PA", "source_name": name, "period": period, "res_competitive": res,
                     "res_total": res / (pct / 100) if pct > 0 else None, "source": "PA PUC PAPowerSwitch monthly statistics"})
    tot = rows.pop()
    if abs(sum(r["res_competitive"] for r in rows) - tot["res_competitive"]) > 0.01 * tot["res_competitive"]:
        raise ValueError("PA: utilities do not sum to the statewide residential total")
    return rows


# ---------------------------------------------------------------- New Jersey (NJ BPU PDF)

def new_jersey(path: str) -> list[dict]:
    text = "".join(p.get_text() for p in pymupdf.open(path))
    m = re.search(r"SWITCHING STATISTICS\s*--\s*([A-Za-z]+ \d{4})", text)
    period = pd.to_datetime(m.group(1), format="%B %Y")
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    def firsts(label: str) -> list[float]:
        return [_n(lines[i + 1]) for i, l in enumerate(lines) if l == label and i + 1 < len(lines) and NUM.match(lines[i + 1])]
    switching, gea, eligible = firsts("Switching"), firsts("GEA Participants"), firsts("Eligible")
    order = ["ACE", "JCP&L", "PSE&G", "RECO"]
    if len(eligible) != 5 or len(switching) != 5 or len(gea) != 5:
        raise ValueError(f"NJ: expected 5 blocks (4 utilities + state), got {len(eligible)} in {path}")
    if abs(sum(eligible[:4]) - eligible[4]) > 1:
        raise ValueError("NJ: utility residential accounts do not sum to the state total")
    return [{"state": "NJ", "source_name": u, "period": period, "res_total": eligible[i],
             "res_competitive": switching[i] + gea[i], "res_aggregation": gea[i], "source": "NJ BPU monthly electric switching statistics"}
            for i, u in enumerate(order)]


# ---------------------------------------------------------------- Massachusetts (DOER, added by hand)

RESIDENTIAL_MA = ["R", "R-LI", "R HP", "R-LI HP"]  # standard and low-income residential, with and without heat pump rates


def massachusetts(path: str) -> list[dict]:
    d = pd.read_excel(path, sheet_name="Machine Readable")
    need = {"Year", "Month", "Parent Utility", "Customer Choice Category", "Customer Rate Class", "Sum of Number of Customers"}
    if not need <= set(d.columns):
        raise ValueError(f"MA: unexpected columns {list(d.columns)}")
    d = d[d["Customer Rate Class"].isin(RESIDENTIAL_MA)]
    g = d.pivot_table(index=["Parent Utility", "Year", "Month"], columns="Customer Choice Category",
                      values="Sum of Number of Customers", aggfunc="sum").fillna(0).reset_index()
    rows = []
    for r in g.to_dict("records"):
        basic, comp, agg = r.get("Basic Service", 0), r.get("Competitive Supply", 0), r.get("Municipal Aggregation", 0)
        rows.append({"state": "MA", "source_name": r["Parent Utility"], "period": pd.Timestamp(int(r["Year"]), int(r["Month"]), 1),
                     "res_total": basic + comp + agg, "res_competitive": comp + agg, "res_aggregation": agg,
                     "source": "Massachusetts DOER customer choice data"})
    if not rows:
        raise ValueError("MA: no residential rows")
    return rows


PARSERS = {"IL_": illinois, "PA_": pennsylvania, "NJ_": new_jersey, "MA_": massachusetts}


def build() -> pd.DataFrame:
    rows = []
    files = _newest()
    for f in sorted(glob.glob(str(ROOT / "reference" / "state_choice" / "*"))):  # added by hand
        files[Path(f).name] = f
    for name, path in files.items():
        for prefix, fn in PARSERS.items():
            if name.startswith(prefix):
                rows += fn(path)
    df = pd.DataFrame(rows)
    ids = pd.read_csv(ROOT / "reference" / "state_choice_utilities.csv")[["state", "source_name", "utility_id_eia"]]
    df = df.merge(ids, on=["state", "source_name"], how="left")
    if df.utility_id_eia.isna().any():
        raise ValueError(f"unmapped utilities: {df[df.utility_id_eia.isna()].source_name.unique()}")
    # Combine companies EIA reports as one utility (FirstEnergy Pennsylvania)
    df = (df.groupby(["state", "utility_id_eia", "period", "source"], as_index=False)
            .agg(res_total=("res_total", "sum"), res_competitive=("res_competitive", "sum"),
                 res_aggregation=("res_aggregation", lambda s: s.sum(min_count=1)),
                 source_names=("source_name", lambda s: "; ".join(sorted(set(s))))))
    df["competitive_share"] = df.res_competitive / df.res_total
    return df.drop_duplicates(["state", "utility_id_eia", "period"], keep="last").sort_values(["state", "utility_id_eia", "period"])


def run() -> None:
    if not glob.glob(str(RAW / "state_choice" / "*" / "*")) and not glob.glob(str(ROOT / "reference" / "state_choice" / "*")):
        print("state_choice: no snapshots yet; skipping")
        return
    write(build(), STAGED, "state_choice")


if __name__ == "__main__":
    d = build()
    print(d.sort_values("period").groupby(["state", "utility_id_eia"]).tail(1).to_string())
