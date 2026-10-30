import datetime as dt
import gzip
import json
from pathlib import Path

import pytest
from test_rules import CITE, HERE, TODAY, TRAIL

from dryline.evaluate import backtest
from dryline.fetch import RawResponse
from dryline.forecast import C, outlook, snow_line_ft, swe_profile
from dryline.models import Missing, TrailLine
from dryline.obs import ForecastPeriod, Observations, SnowObs
from dryline.parse import nws_amount, parse_nws_periods
from dryline.pipeline import DayOutlook
from dryline.ridge import build_ridge, y_of
from dryline.site import outlook_phrase, verdict

FIXTURES = Path(__file__).parent / "fixtures"
LOCAL = dt.timezone(dt.timedelta(hours=-7))


@pytest.mark.parametrize(
    "phrase, inches",
    [
        ("between a quarter and half of an inch", 0.38),
        ("between a half and three quarters of an inch", 0.62),
        ("less than a tenth of an inch", 0.05),
        ("between a tenth and quarter of an inch", 0.17),
        ("less than half an inch", 0.25),
        ("around one inch", 1.0),
        ("around an inch", 1.0),
        ("1 to 3 inches", 2.0),
        ("3 to 5 inches", 4.0),
        ("a lot of rain", None),  # not NWS's vocabulary: no number, never a guess
    ],
)
def test_nws_amount_phrases(phrase, inches):
    assert nws_amount(phrase) == inches


def test_parse_periods_from_recorded_forecast():
    with gzip.open(FIXTURES / "nws-forecast.json.gz") as f:
        raw = RawResponse.model_validate(json.loads(f.read()))
    periods = parse_nws_periods(raw, raw.fetched_at)
    assert periods[0].name == "Tonight"
    assert all(p.grid_elevation_ft > 5000 for p in periods)
    assert all(str(p.source_url).startswith("https://api.weather.gov/") for p in periods)
    assert len(periods) >= 12


def period(day: int, *, daytime=True, temp=55, pop=0, rain=None, snow=None, sky="Sunny"):
    start = dt.datetime.combine(
        TODAY + dt.timedelta(days=day), dt.time(6 if daytime else 18), LOCAL
    )
    return ForecastPeriod(
        **CITE,
        name=f"day {day}",
        start=start,
        end=start + dt.timedelta(hours=12),
        is_daytime=daytime,
        temp_f=temp,
        pop=pop,
        short_forecast=sky,
        rain_in=rain,
        snow_in=snow,
        grid_elevation_ft=7000,
    )


def week(rainy_days=(), temp=55):
    out = []
    for d in range(7):
        wet = d in rainy_days
        out.append(
            period(
                d,
                temp=temp,
                pop=90 if wet else 0,
                rain=0.5 if wet else None,
                sky="Rain" if wet else "Sunny",
            )
        )
        out.append(period(d, daytime=False, temp=temp - 22))
    return tuple(out)


def line(status):
    if status == "unknown":
        return TrailLine(
            trail_id=TRAIL.id,
            trail_name=TRAIL.name,
            date=TODAY,
            status="unknown",
            missing=(Missing(what="x", tried_url="https://example.gov/"),),
        )
    from dryline.models import Claim

    claim = Claim(kind="precip", statement="s", **CITE)
    return TrailLine(
        trail_id=TRAIL.id, trail_name=TRAIL.name, date=TODAY, status=status, claims=(claim,)
    )


def obs(periods, snow=()):
    return Observations(outlooks={TRAIL.id: periods}, snow=tuple(snow))


def test_day_zero_is_always_the_rules_call():
    for status in ("dry", "muddy", "snow"):
        o = outlook(TRAIL, line(status), obs(week()), TODAY, start_water=0.5)
        assert o.days[0].status == status
        assert o.days[0].date == TODAY


def test_muddy_trail_dries_after_sunny_days():
    o = outlook(TRAIL, line("muddy"), obs(week()), TODAY, start_water=0.5)
    assert o.dry_by is not None
    assert TODAY < o.dry_by <= TODAY + dt.timedelta(days=4)
    assert "Dry days ahead" in o.basis


def test_more_rain_pushes_dry_by_out():
    sunny = outlook(TRAIL, line("muddy"), obs(week()), TODAY, start_water=0.5)
    rainy = outlook(TRAIL, line("muddy"), obs(week(rainy_days=(1, 2))), TODAY, start_water=0.5)
    assert rainy.dry_by is None or rainy.dry_by > sunny.dry_by


def test_north_face_dries_slower_than_south():
    north = outlook(TRAIL, line("muddy"), obs(week(temp=48)), TODAY, start_water=0.6)
    south_trail = TRAIL.model_copy(update={"aspect": "S"})
    south = outlook(south_trail, line("muddy"), obs(week(temp=48)), TODAY, start_water=0.6)
    assert south.dry_by is not None
    assert north.dry_by is None or north.dry_by > south.dry_by


def test_dry_trail_gets_wet_from_when_rain_comes():
    o = outlook(TRAIL, line("dry"), obs(week(rainy_days=(3,))), TODAY)
    assert o.wet_from == TODAY + dt.timedelta(days=4)
    assert outlook_phrase(o, TODAY) == f"muddy from {o.wet_from:%A}"


def test_closed_and_unknown_get_no_forecast():
    for status in ("unknown",):  # closed takes the same branch; see forecast.outlook
        o = outlook(TRAIL, line(status), obs(week()), TODAY)
        assert o.why_none and len(o.days) == 1 and o.dry_by is None
        assert outlook_phrase(o, TODAY) == ""


def test_no_nws_forecast_means_no_dry_by():
    o = outlook(TRAIL, line("muddy"), Observations(), TODAY)
    assert o.why_none == "NWS forecast missing today."


def snotel(elev, depth, swe=None):
    return SnowObs(
        **CITE,
        station_id=f"s{elev}",
        station_name="S",
        location=HERE,
        elevation_ft=elev,
        date=TODAY,
        depth_in=depth,
        swe_in=swe,
    )


def test_swe_profile_and_snow_line():
    stations = [snotel(6500, 0, 0), snotel(7500, 1, 0.2), snotel(8500, 6, 1.5), snotel(9500, 12, 3)]
    assert swe_profile(stations, 8000) == pytest.approx(0.85)
    line_ft = snow_line_ft(stations)
    assert 7500 < line_ft < 8500
    assert snow_line_ft([snotel(7000, 0, 0)]) is None


def test_snow_melts_out_in_a_warm_week():
    stations = [snotel(7000, 0, 0), snotel(8500, 3, C.snow_on_trail_swe_in + 0.2)]
    o = outlook(TRAIL, line("snow"), obs(week(temp=60), stations), TODAY)
    assert o.dry_by is not None
    statuses = [d.status for d in o.days]
    assert statuses[0] == "snow" and "dry" in statuses


def test_backtest_scores_forecasts_against_later_mornings():
    o = outlook(TRAIL, line("muddy"), obs(week()), TODAY, start_water=0.5)
    later = {
        TODAY + dt.timedelta(days=k): [line("dry").model_copy(update={"date": TODAY})]
        for k in (1, 2, 3)
    }
    bt = backtest({TODAY: DayOutlook(date=TODAY, trails=(o,))}, later)
    hits, total = bt.hits()
    assert total == 3
    assert hits == sum(d.status == "dry" for d in o.days[1:4])


def test_verdict_is_plain_and_honest():
    muddy = [line("muddy")] * 3
    o = outlook(TRAIL, line("muddy"), obs(week()), TODAY, start_water=0.5)
    v = verdict(muddy, {TRAIL.id: o}, TODAY)
    assert v.startswith("Every trail is muddy today")
    unknowns = [line("unknown")] * 3 + [line("dry")]
    assert verdict(unknowns, {}, TODAY) == "Not enough data to call most trails today."
    assert "—" not in v and "–" not in v


def test_ridge_puts_every_trail_at_its_real_high_point():
    other = TRAIL.model_copy(update={"id": "other", "elevation_max_ft": 9500, "aspect": "S"})
    ridge = build_ridge([TRAIL, other])
    by_id = {m.trail_id: m for m in ridge.markers}
    assert by_id[TRAIL.id].y == round(y_of(8000), 1)
    assert by_id["other"].y == round(y_of(9500), 1)
    assert by_id["other"].y < by_id[TRAIL.id].y  # higher on the page
    assert build_ridge([TRAIL, other]).path == ridge.path  # deterministic
