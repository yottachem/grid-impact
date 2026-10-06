"""Panel regressions on marts/utility_month (inflation-adjusted residential price).

1. Local effect: ln(real price) on ln(trailing-12-month commercial MWh), controlling
   for weather, with utility fixed effects and balancing-authority x month fixed
   effects, so each utility is compared with others in its own regional market in the
   same month. Regional shocks (capacity auctions, fuel) are absorbed.
2. Regional effect: PJM x year event study vs. the rest of the US (reference 2020),
   utility and month fixed effects, weather controls.
3. Within PJM: restructured-state utilities x year vs. regulated PJM utilities.

Standard errors clustered by utility. Coefficients on logs are reported as % changes.
Writes analysis/results/panel_results.md and event-study CSVs."""
from pathlib import Path

import numpy as np
import pandas as pd
import pyfixest as pf

from transform.common import MARTS

OUT = Path(__file__).resolve().parent / "results"
RESTRUCTURED = {"IL", "NJ", "PA", "OH", "MD", "DE", "DC"}


def load() -> pd.DataFrame:
    p = pd.read_parquet(MARTS / "utility_month.parquet")
    p = p[(p.res_price_real_cents_kwh > 0) & (p.res_customers >= 5000)].copy()
    p["unit"] = p.utility_id_eia.astype(int).astype(str) + "_" + p.state
    p["ba"] = p.balancing_authority.fillna("NONE")
    p["ym"] = p.period.dt.strftime("%Y-%m")
    p["year"] = p.period.dt.year
    p["ln_price"] = np.log(p.res_price_real_cents_kwh)
    p["ln_com_ttm"] = np.log(p.com_mwh_ttm.where(p.com_mwh_ttm > 0))
    p["pjm"] = (p.ba == "PJM").astype(int)
    p["restructured"] = p.state.isin(RESTRUCTURED).astype(int)
    p["hdd"], p["cdd"] = p.hdd / 100, p.cdd / 100  # per 100 degree days
    return p.dropna(subset=["hdd", "cdd"])


def pct(b: float) -> float:
    return 100 * (np.exp(b) - 1)


def event_study(df: pd.DataFrame, flag: str) -> pd.DataFrame:
    df = df.copy()
    for y in sorted(df.year.unique()):
        if y != 2020:
            df[f"{flag}_{y}"] = (df[flag] == 1) & (df.year == y)
    terms = " + ".join(f"{flag}_{y}" for y in sorted(df.year.unique()) if y != 2020)
    fit = pf.feols(f"ln_price ~ {terms} + hdd + cdd | unit + ym", data=df, vcov={"CRV1": "unit"})
    t = fit.tidy()
    t = t[t.index.str.startswith(flag)]
    out = pd.DataFrame({"year": [int(i.split("_")[1].split("[")[0].rstrip("]")) for i in t.index],
                        "pct": pct(t.Estimate), "ci_low": pct(t["2.5%"]), "ci_high": pct(t["97.5%"]),
                        "p": t["Pr(>|t|)"]})
    return out, fit


def run() -> str:
    OUT.mkdir(exist_ok=True)
    p = load()
    lines = ["# Panel results", "", f"Sample: {p.unit.nunique()} utility-states, {p.ym.min()} to {p.ym.max()}, "
             f"{len(p):,} utility-months. Outcome: ln(inflation-adjusted residential price). SEs clustered by utility.", ""]

    # 1. Local effect within regional market-month
    d1 = p.dropna(subset=["ln_com_ttm"])
    f1 = pf.feols("ln_price ~ ln_com_ttm + hdd + cdd | unit + ba^ym", data=d1, vcov={"CRV1": "unit"})
    b = f1.tidy().loc["ln_com_ttm"]
    import json
    (OUT / "local_elasticity.json").write_text(json.dumps({
        "elasticity": float(b.Estimate), "ci_low": float(b["2.5%"]), "ci_high": float(b["97.5%"]), "p": float(b["Pr(>|t|)"]),
        "pct_at_40pct_load": pct(b.Estimate * np.log(1.4)), "pct_at_40pct_load_lo": pct(b["2.5%"] * np.log(1.4)),
        "pct_at_40pct_load_hi": pct(b["97.5%"] * np.log(1.4)), "n_units": int(p.unit.nunique())}, indent=2))
    lines += ["## 1. Local load growth (within balancing authority and month)", "",
              f"Elasticity of real residential price to the utility's own commercial load: **{b.Estimate:.3f}** "
              f"(95% CI {b['2.5%']:.3f} to {b['97.5%']:.3f}, p = {b['Pr(>|t|)']:.3f}). "
              f"A 40% rise in commercial load (Dominion-scale) implies {pct(b.Estimate * np.log(1.4)):+.1f}% "
              f"(CI {pct(b['2.5%'] * np.log(1.4)):+.1f}% to {pct(b['97.5%'] * np.log(1.4)):+.1f}%) in real residential price "
              "relative to other utilities in the same regional market.", ""]

    # 2. PJM vs rest of US
    es2, _ = event_study(p, "pjm")
    es2.to_csv(OUT / "event_study_pjm.csv", index=False)
    lines += ["## 2. PJM vs. rest of US (reference year 2020)", "", "| Year | PJM difference | 95% CI | p |", "|---|---|---|---|"]
    lines += [f"| {r.year} | {r.pct:+.1f}% | {r.ci_low:+.1f}% to {r.ci_high:+.1f}% | {r.p:.3f} |" for r in es2.itertuples()]

    # 3. Within PJM: restructured vs regulated
    es3, _ = event_study(p[p.pjm == 1], "restructured")
    es3.to_csv(OUT / "event_study_pjm_restructured.csv", index=False)
    lines += ["", "## 3. Within PJM: restructured-state utilities vs. regulated (reference year 2020)", "",
              "| Year | Restructured difference | 95% CI | p |", "|---|---|---|---|"]
    lines += [f"| {r.year} | {r.pct:+.1f}% | {r.ci_low:+.1f}% to {r.ci_high:+.1f}% | {r.p:.3f} |" for r in es3.itertuples()]
    text = "\n".join(lines) + "\n"
    (OUT / "panel_results.md").write_text(text)
    return text


if __name__ == "__main__":
    print(run())
