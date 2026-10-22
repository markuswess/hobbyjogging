import sys

from .reports import daily, debug, summary


def main():
    mode = sys.argv[1]

    if mode == "daily":
        report = daily()

    elif mode == "all":
        report = daily()
        report += "\n\n"
        report += summary("weekly")
        report += "\n\n"
        report += summary("monthly")
        report += "\n\n"
        report += summary("yearly")

    elif mode in ("weekly", "monthly", "yearly"):
        report = summary(mode)

    elif mode == "debug":
        debug()
        sys.exit(0)

    else:
        raise SystemExit(
            "usage: python -m intervals_report "
            "daily|weekly|monthly|yearly|debug|all"
        )

    print(report)


if __name__ == "__main__":
    main()
