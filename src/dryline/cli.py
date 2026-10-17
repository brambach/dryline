"""Command line entry point: dryline collect | build | eval | label."""

from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="dryline", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("collect", help="fetch today's raw sources (network)")
    sub.add_parser("build", help="apply rules and render the site")
    sub.add_parser("eval", help="score labels against archived lines")
    sub.add_parser("label", help="serve the local labeling page")
    args = parser.parse_args(argv)
    print(f"dryline {args.command}: not implemented yet", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
