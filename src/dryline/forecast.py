"""Dry-by forecast: today's call plus the NWS forecast, run forward a day at a time.

This is a guess, and it says so. It's a small water budget, not a model trained on anything:

- Snow sits at the trail's high point as snow water equivalent (SWE), read off nearby SNOTEL
  stations. It melts by degree-days and grows when NWS forecasts snow at that elevation.
- Mud is water in the top of the soil at the trail's middle elevation. Rain and snowmelt add to
  it. Sun, warmth and a south-facing slope take it away.

Day 0 is always the rules' call, so the forecast can never disagree with today's line. Closed and
unknown trails get no forecast. Every number here is a constant you can read, so the eval can
tell us which one is wrong.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import Field

from dryline.models import Claim, Strict, Trail, TrailLine
from dryline.obs import ForecastPeriod, LatLon, Observations, SnowObs, km_between

LOCAL = ZoneInfo("America/Los_Angeles")
DayStatus = Literal["dry", "muddy", "snow", "closed", "unknown"]
# Middle of Lake Tahoe. The basin snow line is read from stations around it.
BASIN_CENTER = LatLon(lat=39.09, lon=-120.03)
LAKE_FT = 6225


@dataclass(frozen=True)
class Constants:
    lapse_f_per_1000ft: float = 3.5  # temperature drop with height
    melt_in_per_degree_day: float = 0.05  # SWE melted per °F above 32 in a day, full sun
    snow_on_trail_swe_in: float = 0.5  # about 2 in of settled snow, the rules' threshold
    snow_density: float = 0.3  # depth -> SWE when a station has no WTEQ
    muddy_water_in: float = 0.25  # same as the rules' muddy threshold
    soil_holds_in: float = 0.6  # past this, rain runs off instead of soaking the tread
    dry_rate_in: float = 0.14  # water a sunny 55°F day takes out of the top soil
    drain_fraction: float = 0.12  # water that drains down each day regardless of sun
    rain_without_amount_in: float = 0.08  # PoP >= 50% but NWS gave no amount
    snow_ratio: float = 10.0  # inches of new snow per inch of water
    basin_radius_km: float = 45.0


C = Constants()

_SKY = (
    ("mostly sunny", 0.9),
    ("mostly clear", 0.9),
    ("partly", 0.75),
    ("mostly cloudy", 0.5),
    ("sunny", 1.0),
    ("clear", 1.0),
    ("cloudy", 0.35),
)
_ASPECT = {"S": 1.25, "SE": 1.15, "SW": 1.15, "E": 1.0, "W": 1.0, "mixed": 1.0}
_ASPECT.update({"N": 0.65, "NE": 0.8, "NW": 0.8})


def sky_factor(short_forecast: str) -> float:
    s = short_forecast.lower()
    if any(w in s for w in ("rain", "snow", "showers", "thunder", "drizzle", "fog")):
        return 0.25
    return next((f for word, f in _SKY if word in s), 0.6)


@dataclass(frozen=True)
class DayWeather:
    """One local day of the NWS forecast, before it's adjusted to a trail's elevation."""

    date: dt.date
    high_f: float | None
    low_f: float | None
    water_in: float  # expected precipitation as water
    snow_level_ft: int | None
    sky: float
    grid_elevation_ft: int
    summary: str
    periods: tuple[ForecastPeriod, ...]


def _expected_water(p: ForecastPeriod) -> float:
    amount = p.rain_in
    if amount is None and p.snow_in is not None:
        amount = p.snow_in / C.snow_ratio
    if amount is None:
        amount = C.rain_without_amount_in if p.pop >= 50 else 0.0
    # NWS amounts assume it happens. Below 50% we only count the expected share.
    return amount if p.pop >= 50 else amount * p.pop / 100


def daily_weather(periods: tuple[ForecastPeriod, ...]) -> list[DayWeather]:
    by_day: dict[dt.date, list[ForecastPeriod]] = {}
    for p in periods:
        # A night period belongs to the day it starts on (Tonight -> today).
        by_day.setdefault(p.start.astimezone(LOCAL).date(), []).append(p)
    days = []
    for date, ps in sorted(by_day.items()):
        highs = [p.temp_f for p in ps if p.is_daytime]
        lows = [p.temp_f for p in ps if not p.is_daytime]
        levels = [p.snow_level_ft for p in ps if p.snow_level_ft]
        day = next((p for p in ps if p.is_daytime), ps[0])
        days.append(
            DayWeather(
                date=date,
                high_f=max(highs) if highs else None,
                low_f=min(lows) if lows else None,
                water_in=round(sum(_expected_water(p) for p in ps), 3),
                snow_level_ft=min(levels) if levels else None,
                sky=sky_factor(day.short_forecast),
                grid_elevation_ft=ps[0].grid_elevation_ft,
                summary=day.short_forecast,
                periods=tuple(ps),
            )
        )
    return days


def at_elevation(temp_f: float, grid_ft: int, elevation_ft: float) -> float:
    return temp_f - C.lapse_f_per_1000ft * (elevation_ft - grid_ft) / 1000


def falls_as_snow(w: DayWeather, elevation_ft: float) -> bool:
    if w.snow_level_ft is not None:
        return elevation_ft >= w.snow_level_ft
    if any(p.snow_in for p in w.periods):
        # NWS mentioned snow but no level: snow where it's near freezing at that height.
        warmest = w.high_f if w.high_f is not None else w.low_f
        return warmest is not None and at_elevation(warmest, w.grid_elevation_ft, elevation_ft) < 38
    return False


def step(
    swe: float, water: float, w: DayWeather, elevation_ft: float, aspect: str
) -> tuple[float, float]:
    """One day at one elevation. Returns the new (swe, soil water)."""
    high = w.high_f if w.high_f is not None else (w.low_f or 40) + 15
    t = at_elevation(high, w.grid_elevation_ft, elevation_ft)
    sun = w.sky * _ASPECT.get(aspect, 1.0)
    if falls_as_snow(w, elevation_ft):
        swe += w.water_in
    else:
        water += w.water_in
    melt = min(swe, C.melt_in_per_degree_day * max(0.0, t - 32) * max(sun, 0.3))
    swe -= melt
    water += melt
    water = min(water, C.soil_holds_in)
    if swe < 0.05:  # snow on the ground keeps the soil under it wet
        warmth = min(max((t - 35) / 20, 0.1), 1.6)
        water -= C.dry_rate_in * warmth * sun
        water *= 1 - C.drain_fraction
    return max(swe, 0.0), max(water, 0.0)


def classify(swe_top: float, water_mid: float) -> DayStatus:
    if swe_top >= C.snow_on_trail_swe_in:
        return "snow"
    if water_mid >= C.muddy_water_in:
        return "muddy"
    return "dry"


# --- Starting state from today's observations ---------------------------------------------


def latest_snow(snow: tuple[SnowObs, ...], today: dt.date, max_age_days: int = 2) -> list[SnowObs]:
    latest: dict[str, SnowObs] = {}
    for o in snow:
        if today - dt.timedelta(days=max_age_days) <= o.date <= today and (
            o.station_id not in latest or o.date > latest[o.station_id].date
        ):
            latest[o.station_id] = o
    return sorted(latest.values(), key=lambda o: o.elevation_ft)


def _swe(o: SnowObs) -> float:
    if o.swe_in is not None:
        return max(o.swe_in, 0.0)
    return max(o.depth_in, 0.0) * C.snow_density


def swe_profile(stations: list[SnowObs], elevation_ft: float) -> float | None:
    """SWE at an elevation, read linearly between the stations either side of it."""
    if not stations:
        return None
    pts = sorted((o.elevation_ft, _swe(o)) for o in stations)
    if elevation_ft <= pts[0][0]:
        e0, s0 = pts[0]
        # Below the lowest station, snow tapers to nothing over 1,000 ft.
        return max(0.0, s0 * (1 - (e0 - elevation_ft) / 1000))
    if elevation_ft >= pts[-1][0]:
        return pts[-1][1]
    for (e0, s0), (e1, s1) in zip(pts, pts[1:], strict=False):
        if e0 <= elevation_ft <= e1:
            f = (elevation_ft - e0) / (e1 - e0) if e1 > e0 else 0
            return s0 + f * (s1 - s0)
    return None


def nearby(stations: list[SnowObs], where: LatLon, radius_km: float) -> list[SnowObs]:
    return [o for o in stations if km_between(where, o.location) <= radius_km]


def snow_line_ft(stations: list[SnowObs]) -> int | None:
    """Lowest elevation where the snow on the ground stays at or above the threshold all the way
    up. None when no station reports snow."""
    if not any(_swe(o) >= C.snow_on_trail_swe_in for o in stations):
        return None
    line = None
    for e in range(11000, 5900, -50):
        if (swe_profile(stations, e) or 0) >= C.snow_on_trail_swe_in:
            line = e
        else:
            break
    return line


# --- The forecast ----------------------------------------------------------------------------


class OutlookDay(Strict):
    date: dt.date
    status: DayStatus
    weather: str = ""  # "Sunny, 53°F" at the trail
    swe_in: float = 0.0
    water_in: float = 0.0


class TrailOutlook(Strict):
    trail_id: str
    issued: dt.date
    days: tuple[OutlookDay, ...]
    dry_by: dt.date | None = None  # muddy or snow today: first day it's likely dry
    wet_from: dt.date | None = None  # dry today: first day it likely isn't
    horizon: dt.date | None = None  # last forecast day
    sources: tuple[Claim, ...] = ()
    basis: str = ""  # one plain sentence on what drove the call
    why_none: str = Field(default="", description="why there's no forecast, when there isn't")


def start_water(trail: Trail, obs: Observations, now: dt.datetime) -> float:
    """Most recent 48 h precipitation at the nearest fresh gauge, as the soil's starting water."""
    fresh = [
        o
        for o in obs.precip
        if dt.timedelta(hours=-1) <= now - o.window_end <= dt.timedelta(hours=30)
        and min(km_between(trail.trailhead, o.location), 999) <= 40
    ]
    if not fresh:
        return 0.0
    return max(o.total_in for o in fresh)


def _trail_mid(trail: Trail) -> float:
    return (trail.elevation_min_ft + trail.elevation_max_ft) / 2


def outlook(
    trail: Trail, line: TrailLine, obs: Observations, today: dt.date, start_water: float = 0.0
) -> TrailOutlook:
    periods = obs.outlooks.get(trail.id, ())
    if line.status in ("closed", "unknown"):
        why = (
            "Closed trails don't get a forecast."
            if line.status == "closed"
            else ("No forecast without a call for today.")
        )
        return TrailOutlook(
            trail_id=trail.id,
            issued=today,
            days=(OutlookDay(date=today, status=line.status),),
            why_none=why,
        )
    if not periods:
        return TrailOutlook(
            trail_id=trail.id,
            issued=today,
            days=(OutlookDay(date=today, status=line.status),),
            why_none="NWS forecast missing today.",
        )
    weather = [w for w in daily_weather(periods) if w.date >= today]
    stations = nearby(latest_snow(obs.snow, today), trail.trailhead, 40)
    top, mid = trail.elevation_max_ft, _trail_mid(trail)
    swe_top = swe_profile(stations, top) or 0.0
    swe_mid = swe_profile(stations, mid) or 0.0
    swe_mid = min(swe_mid, swe_top)
    water = start_water
    # Day 0 is the rules' call. Nudge the starting state so the model agrees with it.
    if line.status == "snow":
        swe_top = max(swe_top, C.snow_on_trail_swe_in + 0.1)
    else:
        swe_top = min(swe_top, C.snow_on_trail_swe_in - 0.05)
    water = min(water, C.soil_holds_in)
    if line.status == "muddy":
        water = max(water, C.muddy_water_in + 0.05)
    elif line.status == "dry":
        water = min(water, C.muddy_water_in - 0.1)
        swe_mid = 0.0

    days = [OutlookDay(date=today, status=line.status)]
    first = weather[0] if weather and weather[0].date == today else None
    if first:
        days[0] = days[0].model_copy(update={"weather": _weather_text(first, mid)})
    for w in weather:
        if w.date == today:
            # Today's weather still matters for tomorrow's ground.
            swe_top, _ = step(swe_top, 0.0, w, top, trail.aspect)
            swe_mid, water = step(swe_mid, water, w, mid, trail.aspect)
            continue
        status = classify(swe_top, water)
        if swe_mid >= C.snow_on_trail_swe_in and status == "dry":
            status = "snow"
        days.append(
            OutlookDay(
                date=w.date,
                status=status,
                weather=_weather_text(w, mid),
                swe_in=round(swe_top, 2),
                water_in=round(water, 2),
            )
        )
        swe_top, _ = step(swe_top, 0.0, w, top, trail.aspect)
        swe_mid, water = step(swe_mid, water, w, mid, trail.aspect)

    dry_by = wet_from = None
    if line.status in ("muddy", "snow"):
        dry_by = next((d.date for d in days[1:] if d.status == "dry"), None)
    elif line.status == "dry":
        wet_from = next((d.date for d in days[1:] if d.status != "dry"), None)
    p0 = periods[0]
    source = p0.claim(
        "forecast",
        f"NWS forecast for this trail's gridpoint ({p0.grid_elevation_ft:,} ft), "
        f"{len(periods)} periods.",
        observed_at=p0.start,
    )
    return TrailOutlook(
        trail_id=trail.id,
        issued=today,
        days=tuple(days),
        dry_by=dry_by,
        wet_from=wet_from,
        horizon=days[-1].date,
        sources=(source,),
        basis=_basis(trail, line.status, weather, dry_by, wet_from),
    )


def _weather_text(w: DayWeather, elevation_ft: float) -> str:
    if w.high_f is None:
        return w.summary
    t = round(at_elevation(w.high_f, w.grid_elevation_ft, elevation_ft))
    return f"{w.summary}, {t}°F"


def _basis(
    trail: Trail,
    status: str,
    weather: list[DayWeather],
    dry_by: dt.date | None,
    wet_from: dt.date | None,
) -> str:
    wet_days = [w for w in weather if w.water_in >= 0.1]
    if status == "dry":
        if wet_from and wet_days:
            w = next((w for w in wet_days if w.date <= wet_from), wet_days[0])
            return f"NWS has {w.water_in:.2f} in coming {w.date:%A}."
        return "No real rain or snow in the NWS forecast."
    if status == "snow":
        if dry_by:
            return (
                f"Snow up top melts out by our math, then the ground needs a day or two. "
                f"{_aspect_note(trail)}"
            ).strip()
        return f"Not enough warm days in the forecast to melt it out. {_aspect_note(trail)}".strip()
    if dry_by:
        return f"Dry days ahead in the forecast. {_aspect_note(trail)}".strip()
    if wet_days:
        return f"More rain or snow coming before it can dry. {_aspect_note(trail)}".strip()
    return f"Cool and cloudy, so it dries slowly. {_aspect_note(trail)}".strip()


def _aspect_note(trail: Trail) -> str:
    return {
        "N": "North-facing, so it holds water longer.",
        "NE": "Faces northeast, so it dries slower.",
        "NW": "Faces northwest, so it dries slower.",
        "S": "South-facing, so it dries fast.",
        "SE": "Faces southeast and gets morning sun.",
        "SW": "Faces southwest and gets afternoon sun.",
    }.get(trail.aspect, "")


# --- Basin snow line through the week -------------------------------------------------------


class SnowLineDay(Strict):
    date: dt.date
    snow_line_ft: int | None  # None: no snow on the ridge
    kind: Literal["past", "today", "forecast"]


def basin_snow_lines(
    obs: Observations, trails: list[Trail], today: dt.date
) -> tuple[SnowLineDay, ...]:
    """Today's snow line from SNOTEL, then the same budget run forward at every elevation."""
    stations = nearby(latest_snow(obs.snow, today), BASIN_CENTER, C.basin_radius_km)
    if not stations:
        return ()
    line = snow_line_ft(stations)
    out = [SnowLineDay(date=today, snow_line_ft=line, kind="today")]
    # Use the forecast for the trail nearest the lake's middle as the basin's weather.
    central = min(
        (t for t in trails if t.id in obs.outlooks),
        key=lambda t: km_between(t.trailhead, BASIN_CENTER),
        default=None,
    )
    if central is None:
        return tuple(out)
    weather = [w for w in daily_weather(obs.outlooks[central.id]) if w.date >= today]
    grid = list(range(6000, 11001, 100))
    swe = {e: swe_profile(stations, e) or 0.0 for e in grid}
    for w in weather:
        if w.date > today:
            out.append(SnowLineDay(date=w.date, snow_line_ft=_line_from(swe), kind="forecast"))
        swe = {e: step(s, 0.0, w, e, "mixed")[0] for e, s in swe.items()}
    return tuple(out)


def _line_from(swe: dict[int, float]) -> int | None:
    line = None
    for e in sorted(swe, reverse=True):
        if swe[e] >= C.snow_on_trail_swe_in:
            line = e
        else:
            break
    return line


def snow_line_on(obs: Observations, day: dt.date) -> int | None:
    """Just the observed snow line for a past day, for the season replay."""
    return snow_line_ft(nearby(latest_snow(obs.snow, day), BASIN_CENTER, C.basin_radius_km))
