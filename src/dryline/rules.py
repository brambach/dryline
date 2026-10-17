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
    snotel_precip_max_age_hours: int = 30  # daily totals lag about a day
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
    # No snowy station at or below the trail's high point. "Dry" still needs a bare station
    # near the high point; snow reported only higher up is not evidence of bare ground.
    bare = [
        o
        for o in stations
        if o.depth_in < t.snow_depth_in
        and o.elevation_ft >= trail.elevation_max_ft - t.elevation_band_ft
    ]
    if not bare:
        return (
            [],
            [],
            [
                Missing(
                    what=(
                        f"No SNOTEL station within {t.station_radius_km:.0f} km and "
                        f"{_ft(t.elevation_band_ft)} ft of the {_ft(trail.elevation_max_ft)} ft "
                        "high point reported bare ground, so snow up high can't be ruled out"
                    ),
                    tried_url=SNOTEL_URL,
                )
            ],
        )
    # Best witness: a bare station at or above the high point, else the highest; nearest first.
    top = min(
        bare,
        key=lambda o: (
            o.elevation_ft < trail.elevation_max_ft,
            round(_km(trail, o)),
            -o.elevation_ft,
        ),
    )
    claims = [top.claim("snow", f"No snow at similar elevation: {describe(top)}.")]
    if snowy:
        low = snowy[0]
        statement = (
            f"Snow likely only above ~{_ft(low.elevation_ft)} ft, higher than this trail's "
            f"{_ft(trail.elevation_max_ft)} ft high point: {describe(low)}."
        )
        claims.append(low.claim("snow", statement))
    return [], claims, []


def _window_text(o: PrecipObs) -> str:
    if o.network == "SNOTEL":
        first = o.window_start.date()
        last = (o.window_end - dt.timedelta(days=1)).date()
        return f"on {first:%b %-d}–{last:%-d}" if first != last else f"on {first:%b %-d}"
    hours = round((o.window_end - o.window_start).total_seconds() / 3600)
    return f"in the {hours} h to {o.window_end.astimezone(LOCAL):%-I:%M%p %b %-d}".replace(
        "AM", "am"
    ).replace("PM", "pm")


def precip_evidence(
    trail: Trail, precip: tuple[PrecipObs, ...], now: dt.datetime, t: Thresholds = DEFAULT
) -> tuple[list[Claim], list[Claim], list[Missing]]:
    """Returns (wet_claims, dry_claims, missing). Uses the nearest fresh station per network.

    Rain at or above the threshold counts whatever the coverage. "Little rain" needs a gauge that
    can show absence (dry_capable) and enough reporting periods.
    """
    wet: list[Claim] = []
    dry: list[Claim] = []
    for network in ("SNOTEL", "NWS"):
        max_age = (
            dt.timedelta(hours=t.snotel_precip_max_age_hours)
            if network == "SNOTEL"
            else dt.timedelta(hours=t.nws_max_age_hours)
        )
        candidates = [
            o
            for o in precip
            if o.network == network
            and -dt.timedelta(hours=1) <= now - o.window_end <= max_age
            and _km(trail, o) <= t.station_radius_km
        ]
        if not candidates:
            continue
        o = min(candidates, key=lambda o: _km(trail, o))
        where = f"{o.station_name} ({o.network}, {_km(trail, o):.0f} km away)"
        when = _window_text(o)
        if o.total_in >= t.muddy_precip_in:
            wet.append(
                o.claim(
                    "precip",
                    f"Likely muddy: {o.total_in:.2f} in of precipitation {when} at {where}.",
                    observed_at=o.window_end,
                )
            )
        elif (
            o.dry_capable
            and o.periods_expected > 0
            and o.periods_reported / o.periods_expected >= t.precip_min_coverage
        ):
            dry.append(
                o.claim(
                    "precip",
                    f"No measurable rain {when} at {where}."
                    if o.total_in == 0
                    else f"Little rain: {o.total_in:.2f} in {when} at {where}.",
                    observed_at=o.window_end,
                )
            )
    if wet or dry:
        return wet, dry, []
    return (
        [],
        [],
        [
            Missing(
                what=(
                    f"No gauge within {t.station_radius_km:.0f} km had complete, recent "
                    f"precipitation data (SNOTEL daily within {t.snotel_precip_max_age_hours} h, "
                    f"ASOS hourly within {t.nws_max_age_hours} h)"
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
    fresh = [c for c in matches if 0 <= (today - c.last_updated).days <= t.conditions_max_age_days]
    missing = []
    if conditions and not matches:
        missing.append(
            Missing(
                what=(
                    f"Segment {trail.trta_segment} not found on the "
                    f"{conditions[0].source_name} page"
                ),
                tried_url=conditions[0].source_url,
            )
        )
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


def closure_claims(trail: Trail, obs: Observations, today: dt.date) -> list[Claim]:
    claims = []
    for c in obs.closures:
        if c.page not in trail.status_sources:
            continue
        if c.published is not None and c.published > today:
            continue  # announced, not in effect yet
        text = f"{c.title} {c.summary}".lower()
        hit = next((k for k in trail.closure_keywords if k in text), None)
        if hit:
            claims.append(
                c.claim("closure", f"Closed per official alert: “{c.title}” (matched “{hit}”).")
            )
    return claims


def evaluate(
    trail: Trail,
    obs: Observations,
    now: dt.datetime,
    t: Thresholds = DEFAULT,
    today: dt.date | None = None,
) -> TrailLine:
    """`now` sets freshness; `today` (default: now in Pacific time) is the digest date."""
    today = today or now.astimezone(LOCAL).date()
    missing: list[Missing] = []

    closed = closure_claims(trail, obs, today)
    snow, snow_free, m = snow_evidence(trail, obs.snow, today, t)
    missing += m
    wet, dry, m = precip_evidence(trail, obs.precip, now, t)
    missing += m
    cond, m = conditions_for(trail, obs.conditions, today, t)
    missing += m
    missing += [g.missing() for g in obs.gaps if g.source in trail.status_sources]
    notes: list[Claim] = []
    for c in cond:
        statement = f"{c.source_name}, {c.segment} (updated {c.last_updated:%b %-d}): “{c.text}”"
        # A "free of snow" entry is context only: dry needs a fresh SNOTEL reading.
        bucket = {"closed": closed, "snow": snow, "muddy": wet}.get(c.hint, notes)
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
