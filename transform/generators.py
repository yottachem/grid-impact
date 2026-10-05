"""Stage EIA-860M: one row per generator with inventory status (operating, planned,
retired, canceled), capacity, technology, fuel, balancing authority, and key dates.
Each monthly snapshot is kept, so later work can track retirements that slip."""
import pandas as pd

from transform.common import STAGED, latest, snapshot_date, write

SHEETS = {"Operating": "operating", "Planned": "planned", "Retired": "retired", "Canceled or Postponed": "canceled"}
RENAME = {"Entity ID": "entity_id", "Entity Name": "entity_name", "Plant ID": "plant_id", "Plant Name": "plant_name",
          "Plant State": "state", "County": "county", "Balancing Authority Code": "balancing_authority",
          "Sector": "sector", "Generator ID": "generator_id", "Nameplate Capacity (MW)": "nameplate_mw",
          "Net Summer Capacity (MW)": "summer_mw", "Technology": "technology", "Energy Source Code": "fuel",
          "Status": "status", "Latitude": "lat", "Longitude": "lon",
          "Operating Year": "operating_year", "Operating Month": "operating_month",
          "Planned Operation Year": "planned_operation_year", "Planned Operation Month": "planned_operation_month",
          "Planned Retirement Year": "planned_retirement_year", "Planned Retirement Month": "planned_retirement_month",
          "Retirement Year": "retirement_year", "Retirement Month": "retirement_month"}


def build() -> pd.DataFrame:
    f = latest("eia860m", "generators.xlsx")
    frames = []
    for sheet, inv in SHEETS.items():
        d = pd.read_excel(f, sheet, header=2)
        d = d[[c for c in d.columns if c in RENAME]].rename(columns=RENAME)
        d = d[pd.to_numeric(d.plant_id, errors="coerce").notna()]  # drop footnote rows
        d["inventory"] = inv
        frames.append(d)
    df = pd.concat(frames, ignore_index=True)
    for c in ["nameplate_mw", "summer_mw", "lat", "lon"] + [c for c in df.columns if c.endswith(("_year", "_month"))]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["snapshot"] = snapshot_date(f)
    return df


def run() -> None:
    write(build(), STAGED, "generators_860m")


if __name__ == "__main__":
    run()
