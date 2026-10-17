"""Static site: today, a page per trail, an archive, RSS, and JSON. Renders TrailLines only."""

from __future__ import annotations

import datetime as dt
import json
import shutil
from collections import Counter
from email.utils import format_datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from jinja2 import Environment, PackageLoader, StrictUndefined, select_autoescape
from pydantic import TypeAdapter
from selectolax.lexbor import LexborHTMLParser as HTMLParser

from dryline.models import STATUSES, Trail, TrailLine

LOCAL = ZoneInfo("America/Los_Angeles")
ORDER = {"dry": 0, "muddy": 1, "snow": 2, "closed": 3, "unknown": 4}
LABEL = {
    "dry": "Likely dry",
    "muddy": "Likely muddy",
    "snow": "Snow",
    "closed": "Closed",
    "unknown": "Unknown",
}
SITE_URL = "https://brambach.github.io/dryline/"

Lines = TypeAdapter(list[TrailLine])


class UncitedLine(Exception):
    """A rendered line had no link to a source."""


def load_lines(lines_dir: Path) -> dict[dt.date, list[TrailLine]]:
    days = {}
    for path in sorted(lines_dir.glob("*.json")):
        days[dt.date.fromisoformat(path.stem)] = Lines.validate_json(path.read_text())
    return days


def save_lines(lines_dir: Path, day: dt.date, lines: list[TrailLine]) -> Path:
    lines_dir.mkdir(parents=True, exist_ok=True)
    path = lines_dir / f"{day.isoformat()}.json"
    path.write_bytes(Lines.dump_json(lines, indent=1))
    return path


def local_time(t: dt.datetime) -> str:
    return t.astimezone(LOCAL).strftime("%-I:%M%p").lower()


def local_stamp(t: dt.datetime) -> str:
    return t.astimezone(LOCAL).strftime("%b %-d, %-I:%M%p").replace("AM", "am").replace("PM", "pm")


def _env() -> Environment:
    env = Environment(
        loader=PackageLoader("dryline", "templates"),
        autoescape=select_autoescape(["html", "xml"]),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["time"] = local_time
    env.filters["stamp"] = local_stamp
    env.filters["ft"] = lambda n: f"{n:,}"
    env.filters["host"] = lambda u: str(u).split("/")[2].removeprefix("www.")
    env.globals["LABEL"] = LABEL
    return env


def sort_lines(lines: list[TrailLine]) -> list[TrailLine]:
    return sorted(lines, key=lambda line: (ORDER[line.status], line.trail_name))


def summary(lines: list[TrailLine]) -> list[tuple[str, int]]:
    counts = Counter(line.status for line in lines)
    return [(s, counts[s]) for s in STATUSES if counts[s]]


def summary_text(lines: list[TrailLine]) -> str:
    return ", ".join(f"{n} {s}" for s, n in summary(lines))


def check_every_line_linked(html: str) -> int:
    """Each rendered trail line must contain at least one outbound source link."""
    tree = HTMLParser(html)
    rows = tree.css("[data-line]")
    for row in rows:
        if not row.css("a[data-source][href^='http']"):
            raise UncitedLine(row.attributes.get("data-line"))
    return len(rows)


def build_site(
    out: Path,
    days: dict[dt.date, list[TrailLine]],
    trails: list[Trail],
    built_at: dt.datetime,
) -> list[Path]:
    if not days:
        raise ValueError("no lines to render")
    env = _env()
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    written: list[Path] = []
    by_id = {t.id: t for t in trails}
    latest = max(days)
    ordered_days = sorted(days, reverse=True)

    def write(rel: str, text: str, check: bool = False) -> None:
        if check:
            check_every_line_linked(text)
        path = out / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        written.append(path)

    def day_page(day: dt.date, root: str, is_today: bool) -> str:
        lines = sort_lines(days[day])
        return env.get_template("day.html").render(
            root=root,
            day=day,
            is_today=is_today,
            lines=lines,
            summary=summary(lines),
            trails=by_id,
            built_at=built_at,
        )

    write("index.html", day_page(latest, "", True), check=True)
    for day in ordered_days:
        write(f"archive/{day}/index.html", day_page(day, "../../", False), check=True)
        write(f"archive/{day}.json", Lines.dump_json(days[day], indent=1).decode())
    write("today.json", Lines.dump_json(days[latest], indent=1).decode())
    write(
        "archive/index.html",
        env.get_template("archive.html").render(
            root="../",
            days=[(d, summary(days[d])) for d in ordered_days],
            built_at=built_at,
        ),
    )
    for trail in trails:
        history = [(d, line) for d in ordered_days for line in days[d] if line.trail_id == trail.id]
        if not history:
            continue
        write(
            f"trails/{trail.id}/index.html",
            env.get_template("trail.html").render(
                root="../../",
                trail=trail,
                line=history[0][1],
                history=history[:30],
                built_at=built_at,
            ),
            check=True,
        )
    write(
        "feed.xml",
        env.get_template("feed.xml").render(
            site_url=SITE_URL,
            items=[(d, sort_lines(days[d]), summary_text(days[d])) for d in ordered_days[:30]],
            rfc822=lambda d: format_datetime(dt.datetime.combine(d, dt.time(7, 0), tzinfo=LOCAL)),
            built_at=format_datetime(built_at),
        ),
    )
    css = Path(__file__).parent / "templates" / "style.css"
    shutil.copy(css, out / "style.css")
    written.append(out / "style.css")
    (out / ".nojekyll").write_text("")
    (out / "manifest.json").write_text(
        json.dumps({"built_at": built_at.isoformat(), "days": [str(d) for d in ordered_days]})
    )
    return written
