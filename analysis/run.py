"""Run analyses after marts are built: capacity cost per household, panel regressions."""
from analysis import capacity_cost, case_studies, exports, panel


def main() -> None:
    print("== capacity_cost"); capacity_cost.run()
    print("== panel"); print(panel.run())
    print("== case_studies"); case_studies.run()
    print("== exports"); exports.run()


if __name__ == "__main__":
    main()
