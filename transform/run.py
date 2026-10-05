"""Build staged tables and marts from the latest raw snapshots, in dependency order."""
from transform import datacenters, eia861m, exposure

STEPS = [("eia861m", eia861m.run), ("datacenters", datacenters.run), ("exposure", exposure.run)]


def main() -> None:
    for name, step in STEPS:
        print(f"== {name}")
        step()


if __name__ == "__main__":
    main()
