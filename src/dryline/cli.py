"""dryline: collect | build | eval | label | resolve."""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from collections import Counter
from pathlib import Path
from zoneinfo import ZoneInfo

LOCAL = ZoneInfo("America/Los_Angeles")


def _now(args) -> dt.datetime:
    if getattr(args, "now", None):
        t = dt.datetime.fromisoformat(args.now)
        return (t if t.tzinfo else t.replace(tzinfo=LOCAL)).astimezone(dt.UTC)
    return dt.datetime.now(dt.UTC)


def _day(args, now: dt.datetime) -> dt.date:
    if getattr(args, "date", None):
        return dt.date.fromisoformat(args.date)
    return now.astimezone(LOCAL).date()


def cmd_collect(args, paths) -> int:
    from dryline.collect import collect
    from dryline.config import load_grid, load_stations, load_trails
    from dryline.fetch import Fetcher

    now = _now(args)
    day = _day(args, now)
    f = Fetcher(paths.raw, day)
    skipped = collect(
        f, load_trails(paths.trails), load_stations(paths.stations), load_grid(paths.grid), now
    )
    for entry in f.log:
        print(entry)
    for s in skipped:
        print(f"skipped (robots.txt): {s}")
    return 0


def cmd_build(args, paths) -> int:
    from dryline.config import load_grid, load_stations, load_trails
    from dryline.pipeline import lines_for_day, snapshot_time
    from dryline.site import build_site, load_lines, save_lines

    now = _now(args)
    day = _day(args, now)
    if not args.now:
        # Judge freshness as of when the day's data was fetched, so rebuilding the same
        # snapshot later (or in CI) gives the same lines.
        now = snapshot_time(paths.raw, day) or now
    built_at = dt.datetime.now(dt.UTC)
    trails = load_trails(paths.trails)
    notes: list[str] = []
    if (paths.raw / day.isoformat()).exists():
        lines = lines_for_day(
            paths.raw,
            day,
            trails,
            load_stations(paths.stations),
            load_grid(paths.grid),
            now,
            notes=notes,
        )
        save_lines(paths.lines, day, lines)
        counts = Counter(line.status for line in lines)
        print(f"{day}: " + ", ".join(f"{n} {s}" for s, n in sorted(counts.items())))
    else:
        print(f"{day}: no raw data; rendering existing lines only")
    for n in notes:
        print(f"note: {n}")
    days = load_lines(paths.lines)
    out = Path(args.out) if args.out else paths.site
    written = build_site(out, days, trails, built_at)
    print(f"wrote {len(written)} files to {out}")
    return 0


def cmd_eval(args, paths) -> int:
    from dryline.evaluate import read_labels, score
    from dryline.site import load_lines

    labels_path = Path(args.labels) if args.labels else paths.labels
    lines_dir = Path(args.lines) if args.lines else paths.lines
    labels = read_labels(labels_path)
    if not labels:
        print(f"{labels_path}: no labels yet. Run `dryline label` to add some.")
        return 0
    report = score(labels, load_lines(lines_dir))
    if any("synthetic" in lab.note.lower() for lab in labels):
        print("NOTE: these labels are SYNTHETIC. The numbers below test the harness only.\n")
    print(report.render())
    return 0


def cmd_label(args, paths) -> int:
    from dryline.label import serve

    serve(paths.lines, Path(args.labels) if args.labels else paths.labels, args.port)
    return 0


def cmd_resolve(args, paths) -> int:
    from dryline.collect import dump_grid, resolve_grid
    from dryline.config import load_trails
    from dryline.fetch import Fetcher

    now = _now(args)
    f = Fetcher(paths.raw, _day(args, now))
    grid = resolve_grid(f, load_trails(paths.trails))
    paths.grid.write_text(dump_grid(grid))
    missing = [t for t, e in grid.trails.items() if e.obs_station is None]
    print(f"resolved {len(grid.trails)} trails; without a METAR station: {missing or 'none'}")
    return 0


def main(argv: list[str] | None = None) -> int:
    from dryline.config import Paths, project_root

    parser = argparse.ArgumentParser(prog="dryline", description=__doc__)
    parser.add_argument("--root", help="project root (default: auto-detect)")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("collect", help="fetch today's raw sources (network)")
    p.add_argument("--date")
    p = sub.add_parser("build", help="apply rules to a day's raw data and render the site")
    p.add_argument("--date")
    p.add_argument("--now", help="ISO time to evaluate freshness against (default: now)")
    p.add_argument("--out", help="site output directory (default: site/)")
    p = sub.add_parser("eval", help="score labels against archived lines")
    p.add_argument("--labels")
    p.add_argument("--lines")
    p = sub.add_parser("label", help="serve the local labeling page")
    p.add_argument("--labels")
    p.add_argument("--port", type=int, default=8765)
    sub.add_parser("resolve", help="look up NWS gridpoints and stations (network, run rarely)")
    args = parser.parse_args(argv)
    paths = Paths(Path(args.root) if args.root else project_root())
    handler = {
        "collect": cmd_collect,
        "build": cmd_build,
        "eval": cmd_eval,
        "label": cmd_label,
        "resolve": cmd_resolve,
    }[args.command]
    return handler(args, paths)


if __name__ == "__main__":
    sys.exit(main())
