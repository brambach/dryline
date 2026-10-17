"""Read one day's raw files, parse them, and apply the rules to every trail."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from dryline.collect import forecast_name
from dryline.config import PAGES, GridFile, StationsFile
from dryline.fetch import load_raw, raw_path
from dryline.models import Trail, TrailLine
from dryline.obs import Gap, Observations
from dryline.parse import (
    ParseError,
    parse_nvparks,
    parse_nws_forecast,
    parse_nws_observations,
    parse_snotel,
    parse_trta,
    parse_usfs_alerts,
)
from dryline.rules import Thresholds, evaluate


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

    path = raw_path(raw_root, day, "snotel", "daily")
    if path.exists():
        try:
            s, p = parse_snotel(load_raw(path), {st.triplet: st for st in stations.snotel})
            snow += s
            precip += p
        except ParseError as e:
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
            except (ParseError, KeyError, ValueError) as e:
                notes.append(f"forecast {trail.id}: {e}")
        st = entry.obs_station
        if st and st.id not in seen_obs:
            seen_obs[st.id] = True
            opath = raw_path(raw_root, day, "nws", f"obs-{st.id}")
            if opath.exists():
                try:
                    precip.append(parse_nws_observations(load_raw(opath), st, now))
                except (ParseError, KeyError, ValueError) as e:
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
        gaps += g

    return Observations(
        snow=tuple(snow),
        precip=tuple(precip),
        closures=tuple(closures),
        conditions=tuple(conditions),
        forecasts=forecasts,
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
    return [evaluate(trail, obs, now, t) for trail in trails]
