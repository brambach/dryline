"""Read one day's raw files, parse them, and apply the rules to every trail."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from dryline.collect import forecast_name
from dryline.config import ASOS_STATIONS, PAGES, GridFile, StationsFile
from dryline.fetch import day_dir, load_raw, raw_path
from dryline.forecast import (
    SnowLineDay,
    TrailOutlook,
    basin_snow_lines,
    outlook,
    snow_line_on,
    start_water,
)
from dryline.models import Strict, Trail, TrailLine
from dryline.obs import Gap, Observations
from dryline.parse import (
    ParseError,
    parse_nvparks,
    parse_nws_forecast,
    parse_nws_observations,
    parse_nws_periods,
    parse_snotel,
    parse_trta,
    parse_usfs_alerts,
)
from dryline.rules import Thresholds, evaluate

# A malformed response must become a gap or a note, never a crashed build.
PARSE_ERRORS = (ParseError, ValueError, KeyError, TypeError, AttributeError)


def snapshot_time(raw_root: Path, day: dt.date) -> dt.datetime | None:
    """Latest fetched_at among a day's raw files: the right 'now' for rebuilding a past day."""
    times = [load_raw(p).fetched_at for p in day_dir(raw_root, day).glob("*/*.json.gz")]
    return max(times) if times else None


def observations_for_day(
    raw_root: Path,
    day: dt.date,
    trails: list[Trail],
    stations: StationsFile,
    grid: GridFile,
    now: dt.datetime,
    notes: list[str] | None = None,
) -> Observations:
    notes = notes if notes is not None else []
    snow, precip, closures, conditions, gaps = [], [], [], [], []
    forecasts = {}
    outlooks = {}

    path = raw_path(raw_root, day, "snotel", "daily")
    if path.exists():
        try:
            s, p = parse_snotel(load_raw(path), {st.triplet: st for st in stations.snotel})
            snow += s
            precip += p
        except PARSE_ERRORS as e:
            notes.append(f"snotel: {e}")

    seen_obs = {}
    for trail in trails:
        entry = grid.trails.get(trail.id)
        if entry is None:
            continue
        fpath = raw_path(raw_root, day, "nws", f"forecast-{forecast_name(entry)}")
        if fpath.exists():
            try:
                forecasts[trail.id] = parse_nws_forecast(load_raw(fpath), now)
                outlooks[trail.id] = parse_nws_periods(load_raw(fpath), now)
            except PARSE_ERRORS as e:
                notes.append(f"forecast {trail.id}: {e}")
        st = entry.obs_station
        if st and st.id not in seen_obs:
            seen_obs[st.id] = True
            opath = raw_path(raw_root, day, "nws", f"obs-{st.id}")
            if opath.exists():
                try:
                    obs = parse_nws_observations(
                        load_raw(opath), st, now, asos=st.id in ASOS_STATIONS
                    )
                    precip.append(obs)
                except PARSE_ERRORS as e:
                    notes.append(f"nws obs {st.id}: {e}")

    used = sorted({s for t in trails for s in t.status_sources})
    for source in used:
        ppath = raw_path(raw_root, day, "pages", source)
        if not ppath.exists():
            gaps.append(
                Gap(
                    source=source,
                    what=f"{PAGES[source].name} was not fetched today",
                    tried_url=PAGES[source].url,
                )
            )
            continue
        try:
            raw = load_raw(ppath)
            if source == "trta":
                c, g = parse_trta(raw)
                conditions += c
            elif source == "nvparks-tahoe":
                c, g = parse_nvparks(raw)
                closures += c
            else:
                c, g = parse_usfs_alerts(raw, source)
                closures += c
        except PARSE_ERRORS as e:
            notes.append(f"{source}: {e}")
            g = [
                Gap(
                    source=source,
                    what=f"{PAGES[source].name} could not be parsed",
                    tried_url=PAGES[source].url,
                )
            ]
        gaps += g

    return Observations(
        snow=tuple(snow),
        precip=tuple(precip),
        closures=tuple(closures),
        conditions=tuple(conditions),
        forecasts=forecasts,
        outlooks=outlooks,
        gaps=tuple(gaps),
    )


def lines_for_day(
    raw_root: Path,
    day: dt.date,
    trails: list[Trail],
    stations: StationsFile,
    grid: GridFile,
    now: dt.datetime,
    thresholds: Thresholds | None = None,
    notes: list[str] | None = None,
) -> list[TrailLine]:
    obs = observations_for_day(raw_root, day, trails, stations, grid, now, notes)
    t = thresholds or Thresholds()
    return [evaluate(trail, obs, now, t, today=day) for trail in trails]


class DayOutlook(Strict):
    """Everything forecast-shaped for one day: per-trail outlooks and the basin snow line."""

    date: dt.date
    trails: tuple[TrailOutlook, ...]
    snow_lines: tuple[SnowLineDay, ...] = ()


def outlook_for_day(
    raw_root: Path,
    day: dt.date,
    trails: list[Trail],
    stations: StationsFile,
    grid: GridFile,
    now: dt.datetime,
    lines: list[TrailLine],
    notes: list[str] | None = None,
) -> DayOutlook:
    obs = observations_for_day(raw_root, day, trails, stations, grid, now, notes)
    by_id = {line.trail_id: line for line in lines}
    outs = tuple(
        outlook(t, by_id[t.id], obs, day, start_water(t, obs, now)) for t in trails if t.id in by_id
    )
    return DayOutlook(date=day, trails=outs, snow_lines=basin_snow_lines(obs, trails, day))


def observed_snow_line(
    raw_root: Path, day: dt.date, trails: list[Trail], stations: StationsFile, grid: GridFile
) -> int | None:
    now = snapshot_time(raw_root, day)
    if now is None:
        return None
    obs = observations_for_day(raw_root, day, trails, stations, grid, now, [])
    return snow_line_on(obs, day)
