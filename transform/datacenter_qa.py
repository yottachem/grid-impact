"""Quality checks on merged data center sites: duplicate detection and facility typing.

Duplicates. Sources (FracTracker especially) sometimes list one building twice: under an
owner LLC and an operator name, or with slightly different names. Nearby buildings of one
operator are usually distinct (Stack NVA05 vs NVA08, QTS DC2 vs DC6), so distance and name
similarity alone are not enough. Rules for a pair within 300 m with the same status:
  - same building code (e.g. both "ATL1") -> duplicate
  - different building codes (ATL01-1 vs ATL01-3, Landbay A vs B) -> distinct
  - no codes, name overlap >= 0.8, and MW within 25% -> duplicate
Everything else within 2 km that shares an operator or most of its name goes to a review
list (marts/datacenter_review.csv) and is not merged. Reviewed pairs are recorded in
reference/datacenter_pair_decisions.csv (keyed on each record's source ID, with evidence)
and override the rules: duplicate or component pairs drop one record, distinct pairs are
kept and leave the review list. The duplicate with less information
(no reported MW, then smaller MW) is dropped from counts and the map.

Facility type. PeeringDB lists network interconnection points as well as data centers.
Unsized records from network carriers are typed "network" and hidden from the map by
default; other unsized records stay as "size not reported"."""
import re

import numpy as np
import pandas as pd

from transform.common import ROOT

DECISIONS = ROOT / "reference" / "datacenter_pair_decisions.csv"

AUTO_RADIUS_M, REVIEW_RADIUS_M = 300, 2000
STOP = {"data", "center", "centre", "campus", "inc", "llc", "the", "of", "dc", "building", "facility",
        "technologies", "communications", "corp", "company", "group", "holdings"}
CARRIERS = ["cogent", "lumen", "level 3", "zayo", "crown castle", "hurricane electric", "exa infrastructure", "verizon",
            "at&t", "windstream", "segra", "lightpath", "firstlight", "frontier", "consolidated communications", "gtt",
            "cox", "comcast", "charter", "spectrum", "centurylink", "uniti", "everstream", "fibertech", "lightower",
            "arelion", "telia", "ntt america", "pccw", "tata", "telx", "brightspeed", "astound", "wave", "ziply"]


def _tokens(x) -> set:
    x = x.lower() if isinstance(x, str) else ""
    return {t for t in re.sub(r"[^a-z0-9 ]", " ", x).split() if len(t) > 2 and t not in STOP}


def _codes(x) -> set:
    """Building identifiers: alphanumerics with digits (ATL1, IAD44, NVA05, DC6, 3) and
    lettered units after words like Landbay, Building, Lot, Phase."""
    x = x.lower() if isinstance(x, str) else ""
    codes = set(re.findall(r"[a-z]*\d+[a-z]?", x))
    codes |= {f"u:{m}" for m in re.findall(r"\b(?:land ?bay|building|bldg|lot|phase|tract|parcel|hall)\s+([a-z0-9]{1,3})\b", x)}
    return codes


def find_pairs(s: pd.DataFrame) -> pd.DataFrame:
    s = s.reset_index(drop=True)
    lat, lon = np.radians(s.lat.to_numpy()), np.radians(s.lon.to_numpy())
    rows = []
    for i in range(len(s)):
        d = 2 * 6371000 * np.arcsin(np.sqrt(np.sin((lat - lat[i]) / 2) ** 2 + np.cos(lat[i]) * np.cos(lat) * np.sin((lon - lon[i]) / 2) ** 2))
        for j in np.where((d < REVIEW_RADIUS_M) & (np.arange(len(s)) > i))[0]:
            a, b = s.loc[i], s.loc[j]
            oa, ob, na, nb = _tokens(a.operator), _tokens(b.operator), _tokens(a["name"]), _tokens(b["name"])
            same_op = bool(oa & ob)
            sim = len(na & nb) / max(1, min(len(na), len(nb))) if na and nb else 0.0
            if not (same_op or sim >= 0.6):
                continue
            ca, cb = _codes(a["name"]), _codes(b["name"])
            ratio = min(a.mw_est, b.mw_est) / max(a.mw_est, b.mw_est) if pd.notna(a.mw_est) and pd.notna(b.mw_est) and max(a.mw_est, b.mw_est) > 0 else np.nan
            if d[j] <= AUTO_RADIUS_M and a.status_group == b.status_group:
                if ca and cb:
                    verdict = "duplicate" if ca == cb else "distinct"
                elif not ca and not cb and sim >= 0.8 and (ratio >= 0.75 or np.isnan(ratio)):
                    verdict = "duplicate"
                else:
                    verdict = "review"
            else:
                verdict = "distinct" if (ca and cb and ca != cb) else "review"
            rows.append({"site_a": a.site_id, "site_b": b.site_id, "meters": round(float(d[j])), "name_a": a["name"], "name_b": b["name"],
                         "operator_a": a.operator, "operator_b": b.operator, "mw_a": a.mw_est, "mw_b": b.mw_est,
                         "status_a": a.status_group, "status_b": b.status_group, "state": a.state, "verdict": verdict})
    return pd.DataFrame(rows)


def drop_target(a: pd.Series, b: pd.Series) -> int:
    """Of a duplicate pair, drop the record with less information."""
    score = lambda r: ((r.mw_basis == "reported") * 2 + pd.notna(r.mw_est), r.mw_est if pd.notna(r.mw_est) else -1)
    return b.site_id if score(a) >= score(b) else a.site_id


def facility_type(s: pd.DataFrame) -> pd.Series:
    text = (s.operator.fillna("") + " " + s["name"].fillna("")).str.lower()
    carrier = text.apply(lambda t: any(c in t for c in CARRIERS))
    unsized = s.mw_est.isna()
    return np.select([unsized & carrier, unsized], ["network", "unsized"], "data_center")


def reviewed(sites: pd.DataFrame) -> tuple[set, set, int]:
    """Apply reviewed decisions. Returns (pairs decided, sites to drop, decisions matched)."""
    if not DECISIONS.exists():
        return set(), set(), 0
    dec = pd.read_csv(DECISIONS, dtype={"id_a": str, "id_b": str}).fillna({"drop": ""})
    key = {(src, str(i)): sid for src, i, sid in zip(sites.primary_source, sites.primary_source_id, sites.site_id)}
    by_id = sites.set_index("site_id")
    decided, drops, matched = set(), set(), 0
    for d in dec.itertuples():
        a, b = key.get((d.source_a, d.id_a)), key.get((d.source_b, d.id_b))
        if a is None or b is None:
            continue  # a record left a source or was renumbered; the pair falls back to the rules
        matched += 1
        decided.add(frozenset((a, b)))
        if d.decision in ("duplicate", "component"):
            if d.drop == "a":
                drops.add(a)
            elif d.drop == "b":
                drops.add(b)
            else:
                drops.add(drop_target(by_id.loc[a].rename(a).to_frame().T.assign(site_id=a).iloc[0],
                                      by_id.loc[b].rename(b).to_frame().T.assign(site_id=b).iloc[0]))
    return decided, drops, matched


def apply(sites: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    live = sites[sites.status_group.isin(["operating", "construction", "proposed"])]
    pairs = find_pairs(live)
    by_id = sites.set_index("site_id")
    decided, drops, matched = reviewed(sites)
    review_drops = len(drops)
    review_mw = float(sites[sites.site_id.isin(drops)].mw_est.fillna(0).sum())
    if len(pairs):
        is_decided = [frozenset((a, b)) in decided for a, b in zip(pairs.site_a, pairs.site_b)]
        pairs.loc[is_decided, "verdict"] = "reviewed"
    for p in pairs[pairs.verdict == "duplicate"].itertuples() if len(pairs) else []:
        if p.site_a in drops or p.site_b in drops:
            continue
        drops.add(drop_target(by_id.loc[p.site_a].rename(p.site_a).to_frame().T.assign(site_id=p.site_a).iloc[0],
                              by_id.loc[p.site_b].rename(p.site_b).to_frame().T.assign(site_id=p.site_b).iloc[0]))
    sites = sites.copy()
    sites["duplicate"] = sites.site_id.isin(drops)
    sites["facility_type"] = facility_type(sites)
    dup = sites[sites.duplicate]
    review = pairs[pairs.verdict == "review"] if len(pairs) else pairs
    kept = sites[~sites.duplicate & sites.status_group.isin(["operating", "construction", "proposed"])]
    qa = {
        "sites": int(len(kept)),
        "mw_reported": int((kept.mw_basis == "reported").sum()), "mw_estimated": int(kept.mw_basis.isin(["floor_area", "land_area"]).sum()),
        "mw_unknown": int((kept.mw_basis == "unknown").sum()),
        "network_facilities": int((kept.facility_type == "network").sum()),
        "duplicates_removed": int(len(dup)), "duplicate_mw_removed": round(float(dup.mw_est.fillna(0).sum())),
        "pairs_reviewed": int(matched), "review_records_removed": int(review_drops), "review_mw_removed": round(review_mw),
        "pairs_checked": int(len(pairs)), "pairs_distinct": int((pairs.verdict == "distinct").sum()) if len(pairs) else 0,
        "pairs_for_review": int(len(review)),
        # Only pairs where both records carry MW can double count
        "review_mw_upper_bound": round(float(review[["mw_a", "mw_b"]].min(axis=1, skipna=False).fillna(0).sum())) if len(review) else 0,
    }
    return sites, review, qa
