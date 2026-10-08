"""Run analyses after marts are built: capacity cost per household, panel regressions."""
from analysis import capacity_cost, case_studies, coverage, exports, narrative, panel, reliability
from transform import tracts


def main() -> None:
    print("== capacity_cost"); capacity_cost.run()
    print("== tracts"); tracts.run()
    print("== panel"); print(panel.run())
    print("== case_studies"); case_studies.run()
    print("== reliability"); reliability.run()
    print("== exports"); exports.run()
    print("== coverage"); coverage.run()  # how much of each state's residential customers the monthly data cover
    stamp()
    print("== narrative"); narrative.run()  # check every findings statement against this run


def stamp() -> None:
    """Record when the analysis last ran and what data it covered (shown on the site)."""
    import json
    from datetime import datetime, timezone
    import pandas as pd
    from transform.common import MARTS, ROOT
    ref = pd.read_csv(ROOT / "reference" / "capacity_auctions.csv")
    attributed = ref.dropna(subset=["dc_attributable_busd"]).delivery_year.max()
    info = {"ran_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "prices_through": pd.read_parquet(MARTS / "utility_month.parquet", columns=["period"]).period.max().strftime("%Y-%m"),
            "capacity_auctions_through": ref.delivery_year.max(), "dc_attribution_through": attributed,
            "manual_inputs": "reference/capacity_auctions.csv, reference/context_facts.csv, reference/pjm_utility_zones.csv, reference/state_choice/ (MA DOER), "
                             "reference/territory_customers.csv, reference/datacenter_pair_decisions.csv"}
    (ROOT / "analysis" / "results" / "run.json").write_text(json.dumps(info, indent=2))
    print("analysis stamp:", info["ran_at"], "prices through", info["prices_through"])


if __name__ == "__main__":
    main()
