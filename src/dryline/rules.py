"""Deterministic rules: observations in, one TrailLine per trail out. No guessing, no LLM.

Precedence: closed > snow > muddy > dry > unknown. "dry" needs positive evidence on both
snow and precipitation; anything we couldn't check becomes a Missing entry.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from zoneinfo import ZoneInfo

from dryline.models import Claim, Missing, Trail, TrailLine
from dryline.obs import (
    ConditionsObs,
    Observations,
    PrecipObs,
    SnowObs,
    km_between,
)


@dataclass(frozen=True)
class Thresholds:
    station_radius_km: float = 40.0
    elevation_band_ft: int = 1000
    snow_depth_in: float = 2.0  # SNOTEL depth sensors read 0-1 in of noise on bare ground
    muddy_precip_in: float = 0.25
    precip_min_coverage: float = 0.6  # ASOS skips hours; KTVL had 34 of 48 hourly METARs
    snotel_max_age_days: int = 2
    nws_max_age_hours: int = 6
    conditions_max_age_days: int = 14


DEFAULT = Thresholds()
LOCAL = ZoneInfo("America/Los_Angeles")
SNOTEL_URL = "https://wcc.sc.egov.usda.gov/awdbRestApi/services/v1/data"
NWS_URL = "https://api.weather.gov/"


def _ft(n: float) -> str:
    return f"{round(n):,}"


def _trail_points(trail: Trail):
    return [p for p in (trail.trailhead, trail.high_point) if p is not None]


def _km(trail: Trail, obs) -> float:
    return min(km_between(p, obs.location) for p in _trail_points(trail))


def snow_evidence(
    trail: Trail, snow: tuple[SnowObs, ...], today: dt.date, t: Thresholds = DEFAULT
) -> tuple[list[Claim], list[Claim], list[Missing]]:
    """Returns (snow_claims, snow_free_claims, missing)."""
    oldest = today - dt.timedelta(days=t.snotel_max_age_days)
    lo = trail.elevation_min_ft - t.elevation_band_ft
    hi = trail.elevation_max_ft + t.elevation_band_ft
    latest: dict[str, SnowObs] = {}
    for o in snow:
        if o.date < oldest or o.date > today:
            continue
        if not lo <= o.elevation_ft <= hi or _km(trail, o) > t.station_radius_km:
            continue
        if o.station_id not in latest or o.date > latest[o.station_id].date:
            latest[o.station_id] = o
    if not latest:
        return (
            [],
            [],
            [
                Missing(
                    what=(
                        f"No SNOTEL station within {t.station_radius_km:.0f} km and "
                        f"{_ft(lo)}–{_ft(hi)} ft reported snow depth in the last "
                        f"{t.snotel_max_age_days} days"
                    ),
                    tried_url=SNOTEL_URL,
                )
            ],
        )
    stations = sorted(latest.values(), key=lambda o: o.elevation_ft)
    snowy = [o for o in stations if o.depth_in >= t.snow_depth_in]
    on_trail = [o for o in snowy if o.elevation_ft <= trail.elevation_max_ft]

    def describe(o: SnowObs) -> str:
        return (
            f"{o.station_name} SNOTEL ({_ft(o.elevation_ft)} ft, {_km(trail, o):.0f} km away) "
            f"reported {o.depth_in:g} in of snow on {o.date:%b %-d}"
        )

    if on_trail:
        low = on_trail[0]
        claim = low.claim(
            "snow",
            f"Snow likely above ~{_ft(low.elevation_ft)} ft (trail tops out at "
            f"{_ft(trail.elevation_max_ft)} ft): {describe(low)}.",
        )
        return [claim], [], []
    # No snowy station at or below the trail's high point.
    covering = [
        o for o in stations if o.elevation_ft >= trail.elevation_max_ft - t.elevation_band_ft
    ]
    if not covering:
        return (
            [],
            [],
            [
                Missing(
                    what=(
                        "No SNOTEL station near the trail's high point "
                        f"({_ft(trail.elevation_max_ft)} ft) reported recently"
                    ),
                    tried_url=SNOTEL_URL,
                )
            ],
        )
    top = max(covering, key=lambda o: o.elevation_ft)
    if snowy:
        low = snowy[0]
        statement = (
            f"Snow likely only above ~{_ft(low.elevation_ft)} ft, higher than this trail's "
            f"{_ft(trail.elevation_max_ft)} ft high point: {describe(low)}."
        )
        return [], [low.claim("snow", statement)], []
    statement = f"No snow at similar elevation: {describe(top)}."
    return [], [top.claim("snow", statement)], []


def precip_evidence(
    trail: Trail, precip: tuple[PrecipObs, ...], now: dt.datetime, t: Thresholds = DEFAULT
) -> tuple[list[Claim], list[Claim], list[Missing]]:
    """Returns (wet_claims, dry_claims, missing). Uses the nearest adequate station per network."""
    wet: list[Claim] = []
    dry: list[Claim] = []
    used = False
    for network in ("SNOTEL", "NWS"):
        max_age = (
            dt.timedelta(days=t.snotel_max_age_days)
            if network == "SNOTEL"
            else dt.timedelta(hours=t.nws_max_age_hours)
        )
        candidates = [
            o
            for o in precip
            if o.network == network
            and now - o.window_end <= max_age
            and o.periods_expected > 0
            and o.periods_reported / o.periods_expected >= t.precip_min_coverage
            and _km(trail, o) <= t.station_radius_km
        ]
        if not candidates:
            continue
        used = True
        o = min(candidates, key=lambda o: _km(trail, o))
        hours = round((o.window_end - o.window_start).total_seconds() / 3600)
        where = f"{o.station_name} ({o.network}, {_km(trail, o):.0f} km away)"
        if o.total_in >= t.muddy_precip_in:
            wet.append(
                o.claim(
                    "precip",
                    f"Likely muddy: {o.total_in:.2f} in of precipitation in the last {hours} h "
                    f"at {where}.",
                    observed_at=o.window_end,
                )
            )
        else:
            dry.append(
                o.claim(
                    "precip",
                    f"Little rain: {o.total_in:.2f} in in the last {hours} h at {where}.",
                    observed_at=o.window_end,
                )
            )
    if used:
        return wet, dry, []
    return (
        [],
        [],
        [
            Missing(
                what=(
                    f"No station within {t.station_radius_km:.0f} km had complete recent "
                    "precipitation data"
                ),
                tried_url=NWS_URL,
            )
        ],
    )


def conditions_for(
    trail: Trail, conditions: tuple[ConditionsObs, ...], today: dt.date, t: Thresholds = DEFAULT
) -> tuple[list[ConditionsObs], list[Missing]]:
    if not trail.trta_segment:
        return [], []
    matches = [c for c in conditions if c.segment == trail.trta_segment]
    fresh = [c for c in matches if (today - c.last_updated).days <= t.conditions_max_age_days]
    missing = []
    if matches and not fresh:
        stale = matches[0]
        missing.append(
            Missing(
                what=(
                    f"{stale.source_name} entry for {stale.segment} was last updated "
                    f"{stale.last_updated:%b %-d}, older than {t.conditions_max_age_days} days"
                ),
                tried_url=stale.source_url,
            )
        )
    return fresh, missing


def closure_claims(trail: Trail, obs: Observations) -> list[Claim]:
    claims = []
    for c in obs.closures:
        if c.page not in trail.status_sources:
            continue
        text = f"{c.title} {c.summary}".lower()
        hit = next((k for k in trail.closure_keywords if k in text), None)
        if hit:
            claims.append(
                c.claim("closure", f"Closed per official alert: “{c.title}” (matched “{hit}”).")
            )
    return claims


def evaluate(
    trail: Trail, obs: Observations, now: dt.datetime, t: Thresholds = DEFAULT
) -> TrailLine:
    today = now.astimezone(LOCAL).date()
    missing: list[Missing] = [g.missing() for g in obs.gaps if g.source in trail.status_sources]

    closed = closure_claims(trail, obs)
    snow, snow_free, m = snow_evidence(trail, obs.snow, today, t)
    missing += m
    wet, dry, m = precip_evidence(trail, obs.precip, now, t)
    missing += m
    cond, m = conditions_for(trail, obs.conditions, today, t)
    missing += m
    notes: list[Claim] = []
    for c in cond:
        statement = f"{c.source_name}, {c.segment} (updated {c.last_updated:%b %-d}): “{c.text}”"
        bucket = {"closed": closed, "snow": snow, "muddy": wet, "snow_free": snow_free}.get(
            c.hint, notes
        )
        bucket.append(c.claim("conditions", statement))

    forecast = None
    if f := obs.forecasts.get(trail.id):
        forecast = f.claim("forecast", f"NWS {f.period}: {f.short_forecast}.", observed_at=f.start)

    if closed:
        status, reasons = "closed", closed
    elif snow:
        status, reasons = "snow", snow
    elif wet:
        status, reasons = "muddy", wet
    elif snow_free and dry:
        status, reasons = "dry", snow_free + dry
    else:
        status, reasons = "unknown", []
    context = [c for c in closed + snow + wet + snow_free + dry + notes if c not in reasons]
    if status == "unknown" and not missing:
        missing.append(
            Missing(
                what="Not enough evidence to call dry: no confirmed snow-free and low-rain reading",
                tried_url=trail.official_status_url,
            )
        )
    if not trail.status_sources:
        missing.append(
            Missing(
                what=f"No official closure source dryline can read for {trail.land_manager}",
                tried_url=trail.official_status_url,
            )
        )
    return TrailLine(
        trail_id=trail.id,
        trail_name=trail.name,
        date=today,
        status=status,
        claims=tuple(reasons),
        context=tuple(context),
        missing=tuple(missing),
        forecast=forecast,
    )
