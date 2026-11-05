import os
import sys

from .cli import extract_source
from .commands import COMMANDS, command_help, usage
from .mdpretty import render_markdown
from .sources import create_source


def main(argv: list[str] | None = None):
    argv = list(sys.argv[1:] if argv is None else argv)
    source_name, include_review, argv = extract_source(argv)

    if argv and argv[0] in ("-h", "--help"):
        print(usage())
        return

    if argv:
        name = argv[0]
        args = argv[1:]
    else:
        name = "daily"
        args = []

    command = COMMANDS.get(name)

    if command is None:
        print(usage(), file=sys.stderr)
        raise SystemExit(2)

    if any(arg in ("-h", "--help") for arg in args):
        print(command_help(command))
        return

    try:
        parsed = command.parse(args) if command.parse else None
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    if command.needs_source:
        try:
            source = create_source(source_name)
        except Exception as exc:
            raise SystemExit(
                f"could not open {source_name} source: {exc}"
            ) from exc

        with source:
            report = command.run(parsed, source, include_review)
    else:
        report = command.run(parsed, None, include_review)

    if report is None:
        return

    if sys.stdout.isatty() and os.environ.get("NO_PRETTY") != "1":
        print(render_markdown(report))
    else:
        print(report)


if __name__ == "__main__":
    main()
