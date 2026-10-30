"""Static site: today on the ridge, a page per trail, an archive, RSS, and JSON.

Renders TrailLines (the rules' call, always cited) and TrailOutlooks (the dry-by guess, which
says it's a guess). Every rendered trail line still has to link a source.
"""

from __future__ import annotations

import datetime as dt
import json
import shutil
import statistics
from collections import Counter
from email.utils import format_datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from jinja2 import Environment, PackageLoader, StrictUndefined, select_autoescape
from pydantic import TypeAdapter
from selectolax.lexbor import LexborHTMLParser as HTMLParser

from dryline.evaluate import backtest
from dryline.forecast import LAKE_FT, TrailOutlook
from dryline.models import STATUSES, Trail, TrailLine
from dryline.pipeline import DayOutlook
from dryline.ridge import build_ridge, short_name

LOCAL = ZoneInfo("America/Los_Angeles")
ORDER = {"dry": 0, "muddy": 1, "snow": 2, "closed": 3, "unknown": 4}
LABEL = {
    "dry": "Likely dry",
    "muddy": "Likely muddy",
    "snow": "Snow",
    "closed": "Closed",
    "unknown": "Unknown",
}
WORD = {"dry": "dry", "muddy": "muddy", "snow": "snow", "closed": "closed", "unknown": "unknown"}
SITE_URL = "https://dryline.brycerambach.com/"
TEMPLATES = Path(__file__).parent / "templates"
# Vendored by design-tokens/sync.sh; edit nothing in there, override in style.css.
TOKENS = TEMPLATES / "design-tokens"
TOKENS_SKIP = ("*.sh", "*.md", "package.json", "VERSION", "SHA256SUMS")

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


def load_outlooks(outlook_dir: Path) -> dict[dt.date, DayOutlook]:
    out = {}
    for path in sorted(outlook_dir.glob("*.json")):
        out[dt.date.fromisoformat(path.stem)] = DayOutlook.model_validate_json(path.read_text())
    return out


def save_outlook(outlook_dir: Path, day_outlook: DayOutlook) -> Path:
    outlook_dir.mkdir(parents=True, exist_ok=True)
    path = outlook_dir / f"{day_outlook.date.isoformat()}.json"
    path.write_text(day_outlook.model_dump_json(indent=1))
    return path


def local_time(t: dt.datetime) -> str:
    return t.astimezone(LOCAL).strftime("%-I:%M%p").lower()


def local_stamp(t: dt.datetime) -> str:
    return t.astimezone(LOCAL).strftime("%b %-d, %-I:%M%p").replace("AM", "am").replace("PM", "pm")


def day_word(d: dt.date, today: dt.date) -> str:
    if d == today:
        return "today"
    if d == today + dt.timedelta(days=1):
        return "tomorrow"
    if (d - today).days < 7:
        return d.strftime("%A")
    return d.strftime("%b %-d")


def outlook_phrase(o: TrailOutlook | None, today: dt.date) -> str:
    """The forecast in a few words, for a row: 'dry by Saturday', 'wet from Tuesday'."""
    if o is None or o.why_none or len(o.days) < 2:
        return ""
    status = o.days[0].status
    if o.dry_by:
        return f"dry by {day_word(o.dry_by, today)}"
    if o.wet_from:
        wet = next(d.status for d in o.days if d.date == o.wet_from)
        return f"{WORD[wet]} from {day_word(o.wet_from, today)}"
    if status == "dry":
        return "dry all week"
    return "not dry this week"


def verdict(lines: list[TrailLine], outlooks: dict[str, TrailOutlook], today: dt.date) -> str:
    """One plain sentence for the top of the page. Honest about unknowns."""
    n = len(lines)
    counts = Counter(line.status for line in lines)
    top, k = counts.most_common(1)[0]
    if top == "unknown" and k > n / 2:
        return "Not enough data to call most trails today."
    if k == n:
        return {
            "dry": "Every trail is dry today.",
            "muddy": "Every trail is muddy today.",
            "snow": "Snow on every trail today.",
            "closed": "Every trail is closed today.",
        }[top]
    lead = f"{k} of {n} trails are {WORD[top]} today."
    if top == "snow":
        lead = f"Snow on {k} of {n} trails today."
    if top in ("muddy", "snow"):
        dry_bys = sorted(o.dry_by for o in outlooks.values() if o.dry_by)
        if len(dry_bys) >= k / 2:
            return f"{lead} Most dry by {day_word(statistics.median_low(dry_bys), today)}."
        return f"{lead} More rain before most of them dry."
    if top == "dry":
        wet = sorted(o.wet_from for o in outlooks.values() if o.wet_from)
        if len(wet) >= k / 2:
            return f"{lead} Rain coming {day_word(statistics.median_low(wet), today)}."
    return lead


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
    env.globals["WORD"] = WORD
    env.globals["MODES"] = json.loads((TOKENS / "tokens.json").read_text())["modes"]
    env.globals["LAKE_FT"] = LAKE_FT
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


def timeline(
    days: dict[dt.date, list[TrailLine]],
    outlooks: dict[dt.date, DayOutlook],
    latest: dt.date,
    past_days: int = 14,
) -> list[dict]:
    """What the ridge can scrub through: past mornings as published, today, then the forecast."""
    out = []
    for d in sorted(days)[-past_days - 1 :]:
        o = outlooks.get(d)
        line_ft = next((s.snow_line_ft for s in o.snow_lines if s.date == d), None) if o else None
        out.append(
            {
                "date": d.isoformat(),
                "label": d.strftime("%a %-d"),
                "kind": "today" if d == latest else "past",
                "snow_line_ft": line_ft,
                "has_line": bool(o and o.snow_lines),
                "status": {line.trail_id: line.status for line in days[d]},
            }
        )
    today = outlooks.get(latest)
    if today:
        future: dict[str, dict] = {}
        for s in today.snow_lines:
            if s.date > latest:
                future[s.date.isoformat()] = {
                    "date": s.date.isoformat(),
                    "label": s.date.strftime("%a %-d"),
                    "kind": "forecast",
                    "snow_line_ft": s.snow_line_ft,
                    "has_line": True,
                    "status": {},
                }
        for o in today.trails:
            for od in o.days[1:]:
                key = od.date.isoformat()
                future.setdefault(
                    key,
                    {
                        "date": key,
                        "label": od.date.strftime("%a %-d"),
                        "kind": "forecast",
                        "snow_line_ft": None,
                        "has_line": False,
                        "status": {},
                    },
                )["status"][o.trail_id] = od.status
        out += [future[k] for k in sorted(future)]
    return out


def build_site(
    out: Path,
    days: dict[dt.date, list[TrailLine]],
    trails: list[Trail],
    built_at: dt.datetime,
    outlooks: dict[dt.date, DayOutlook] | None = None,
) -> list[Path]:
    if not days:
        raise ValueError("no lines to render")
    for lines in days.values():
        for line in lines:
            if not isinstance(line, TrailLine):
                raise TypeError(f"renderer accepts TrailLine only, got {type(line).__name__}")
    outlooks = outlooks or {}
    env = _env()
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    written: list[Path] = []
    by_id = {t.id: t for t in trails}
    latest = max(days)
    ordered_days = sorted(days, reverse=True)
    ridge = build_ridge([t for t in trails if any(ln.trail_id == t.id for ln in days[latest])])
    shorts = {t.id: short_name(t) for t in trails}
    today_outlook = outlooks.get(latest)
    trail_outlooks = {o.trail_id: o for o in today_outlook.trails} if today_outlook else {}
    phrases = {tid: outlook_phrase(o, latest) for tid, o in trail_outlooks.items()}
    tl = timeline(days, outlooks, latest)
    bt = backtest(outlooks, days)

    def write(rel: str, text: str, check: bool = False) -> None:
        if check:
            check_every_line_linked(text)
        path = out / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        written.append(path)

    is_today = latest == built_at.astimezone(LOCAL).date()
    lines = sort_lines(days[latest])
    write(
        "index.html",
        env.get_template("today.html").render(
            root="",
            day=latest,
            is_today=is_today,
            lines=lines,
            summary=summary(lines),
            trails=by_id,
            shorts=shorts,
            outlooks=trail_outlooks,
            phrases=phrases,
            verdict=verdict(lines, trail_outlooks, latest),
            ridge=ridge,
            timeline=json.dumps(tl, separators=(",", ":")),
            built_at=built_at,
            page="today",
        ),
        check=True,
    )
    for day in ordered_days:
        write(
            f"archive/{day}/index.html",
            env.get_template("day.html").render(
                root="../../",
                day=day,
                lines=sort_lines(days[day]),
                summary=summary(days[day]),
                trails=by_id,
                built_at=built_at,
                page="archive",
            ),
            check=True,
        )
        write(f"archive/{day}.json", Lines.dump_json(days[day], indent=1).decode())
    write("today.json", Lines.dump_json(days[latest], indent=1).decode())
    if today_outlook:
        write("outlook.json", today_outlook.model_dump_json(indent=1))
    write(
        "trails.json",
        json.dumps(
            [
                {
                    "id": t.id,
                    "name": t.name,
                    "short": shorts[t.id],
                    "elevation_min_ft": t.elevation_min_ft,
                    "elevation_max_ft": t.elevation_max_ft,
                }
                for t in trails
            ],
            indent=1,
        ),
    )
    write(
        "archive/index.html",
        env.get_template("archive.html").render(
            root="../",
            days=[(d, summary(days[d])) for d in ordered_days],
            built_at=built_at,
            page="archive",
        ),
    )
    snow_today = (
        next((s.snow_line_ft for s in today_outlook.snow_lines if s.date == latest), None)
        if today_outlook
        else None
    )
    for trail in trails:
        history = [(d, ln) for d in ordered_days for ln in days[d] if ln.trail_id == trail.id]
        if not history:
            continue
        write(
            f"trails/{trail.id}/index.html",
            env.get_template("trail.html").render(
                root="../../",
                trail=trail,
                short=shorts[trail.id],
                line=history[0][1],
                outlook=trail_outlooks.get(trail.id),
                phrase=phrases.get(trail.id, ""),
                today=latest,
                snow_line_ft=snow_today,
                history=history[:30],
                built_at=built_at,
                page="trail",
                day_word=day_word,
            ),
            check=True,
        )
    write(
        "mine/index.html",
        env.get_template("mine.html").render(
            root="../",
            trails=sorted(trails, key=lambda t: shorts[t.id]),
            shorts=shorts,
            built_at=built_at,
            page="mine",
        ),
    )
    write(
        "how/index.html",
        env.get_template("how.html").render(
            root="../",
            bt=bt,
            n_days=len(days),
            first_day=min(days),
            built_at=built_at,
            page="how",
        ),
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
    for name in ("style.css", "dryline.js", "favicon.svg"):
        shutil.copy(TEMPLATES / name, out / name)
        written.append(out / name)
    shutil.copytree(TEMPLATES / "fonts", out / "fonts", ignore=shutil.ignore_patterns("*.md"))
    shutil.copytree(TOKENS, out / "design-tokens", ignore=shutil.ignore_patterns(*TOKENS_SKIP))
    written += sorted((out / "design-tokens").rglob("*.css"))
    (out / ".nojekyll").write_text("")
    (out / "manifest.json").write_text(
        json.dumps({"built_at": built_at.isoformat(), "days": [str(d) for d in ordered_days]})
    )
    return written
