"""Analysis panel: EIA-861M utility x state x month joined to that utility's data center
exposure (current snapshot; time-varying exposure needs site online dates, a later step).

Exposure tier uses operating + pipeline MW per 1,000 residential customers:
high >= 10, medium 1-10, low > 0-1, none = 0. Thresholds are fixed for readability and
documented in docs/methods.md."""
import numpy as np
import pandas as pd

from transform.common import MARTS, STAGED, write

TIERS = [(10, "high"), (1, "medium"), (0, "low")]


def tier(x: float) -> str:
    if not np.isfinite(x) or x <= 0:
        return "none"
    return next(name for floor, name in TIERS if x >= floor)


def build() -> pd.DataFrame:
    m = pd.read_parquet(STAGED / "eia861m_utility_month.parquet")
    m = m[~m.is_adjustment & ~m.is_btm]
    u = pd.read_parquet(MARTS / "utility_exposure.parquet")
    u["exposure_per_1k_res"] = (u.mw_op + u.mw_pipeline) / (u.res_customers.where(u.res_customers > 0) / 1000)
    cols = ["utility_id_eia", "state", "balancing_authority", "mw_op", "mw_uc", "mw_pr", "mw_pipeline", "mw_op_per_1k_res",
            "mw_pipeline_per_1k_res", "exposure_per_1k_res"]
    p = m.merge(u[cols], on=["utility_id_eia", "state"], how="left")
    p[["mw_op", "mw_uc", "mw_pr", "mw_pipeline"]] = p[["mw_op", "mw_uc", "mw_pr", "mw_pipeline"]].fillna(0)
    p["exposure_tier"] = p.exposure_per_1k_res.fillna(0).map(tier)
    return p


def run() -> None:
    write(build(), MARTS, "utility_month")


if __name__ == "__main__":
    run()
