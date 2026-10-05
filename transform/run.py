"""Build staged tables and marts from the latest raw snapshots, in dependency order."""
from transform import datacenters, eia861m, exposure, utility_month

STEPS = [("eia861m", eia861m.run), ("datacenters", datacenters.run), ("exposure", exposure.run),
         ("utility_month", utility_month.run)]


def main() -> None:
    for name, step in STEPS:
        print(f"== {name}")
        step()


if __name__ == "__main__":
    main()
