"""Run analyses after marts are built: capacity cost per household, panel regressions."""
from analysis import capacity_cost, panel


def main() -> None:
    print("== capacity_cost"); capacity_cost.run()
    print("== panel"); print(panel.run())


if __name__ == "__main__":
    main()
