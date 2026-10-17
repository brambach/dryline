import datetime as dt

import pytest
from pydantic import ValidationError

from dryline.models import Claim, LatLon, Missing, Trail, TrailLine
from dryline.obs import ClosureObs, ConditionsObs, Gap, Observations, PrecipObs, SnowObs
from dryline.rules import evaluate

NOW = dt.datetime(2026, 10, 17, 14, 0, tzinfo=dt.UTC)
TODAY = NOW.date()
FETCHED = NOW - dt.timedelta(minutes=5)
HERE = LatLon(lat=38.93, lon=-120.05)

TRAIL = Trail(
    id="test-trail",
    name="Test Trail",
    trailhead=HERE,
    elevation_min_ft=6500,
    elevation_max_ft=8000,
    aspect="N",
    land_manager="USFS",
    official_status_url="https://www.fs.usda.gov/example",
    activities=("hike",),
    closure_keywords=("test trail",),
    trta_segment="Test Segment",
    sources=("https://www.fs.usda.gov/example",),
)

CITE = dict(
    source_name="Fixture",
    source_url="https://example.gov/data",
    fetched_at=FETCHED,
    quote="raw value",
)


def snow(elev, depth, days_ago=0, km_north=0.0, sid=None):
    return SnowObs(
        **CITE,
        station_id=sid or f"s{elev}",
        station_name=f"Station {elev}",
        location=LatLon(lat=HERE.lat + km_north / 111, lon=HERE.lon),
        elevation_ft=elev,
        date=TODAY - dt.timedelta(days=days_ago),
        depth_in=depth,
    )


def rain(total, network="SNOTEL", reported=2, expected=2, hours_ago=1):
    end = NOW - dt.timedelta(hours=hours_ago)
    return PrecipObs(
        **CITE,
        network=network,
        station_id="p1",
        station_name="Rain Gauge",
        location=HERE,
        window_start=end - dt.timedelta(hours=48),
        window_end=end,
        total_in=total,
        periods_reported=reported,
        periods_expected=expected,
    )


def run(**kw):
    return evaluate(TRAIL, Observations(**kw), NOW)


def test_dry_needs_snow_free_and_low_rain():
    line = run(snow=(snow(7800, 0),), precip=(rain(0.0),))
    assert line.status == "dry"
    assert len(line.claims) == 2
    assert all(c.source_url and c.fetched_at for c in line.claims)


def test_snow_at_similar_elevation_below_high_point():
    line = run(snow=(snow(7500, 6), snow(8800, 14)), precip=(rain(0.0),))
    assert line.status == "snow"
    assert "Snow likely above ~7,500 ft" in line.claims[0].statement


def test_snow_only_above_trail_is_not_snow():
    line = run(snow=(snow(7900, 0), snow(8800, 10)), precip=(rain(0.0),))
    assert line.status == "dry"
    assert "only above ~8,800 ft" in line.claims[0].statement


def test_snow_depth_noise_below_threshold_is_not_snow():
    line = run(snow=(snow(7800, 1),), precip=(rain(0.0),))
    assert line.status == "dry"


def test_muddy_after_rain():
    line = run(snow=(snow(7800, 0),), precip=(rain(0.6),))
    assert line.status == "muddy"
    assert "0.60 in" in line.claims[0].statement


def test_closed_beats_everything():
    closure = ClosureObs(
        **CITE, title="Test Trail Closure Order", link="https://example.gov/alert/1"
    )
    line = run(snow=(snow(7500, 6),), precip=(rain(1.0),), closures=(closure,))
    assert line.status == "closed"
    assert {c.kind for c in line.context} == {"snow", "precip"}


def test_unrelated_closure_ignored():
    closure = ClosureObs(**CITE, title="Other Road Closure", link="https://example.gov/alert/2")
    assert run(snow=(snow(7800, 0),), precip=(rain(0.0),), closures=(closure,)).status == "dry"


def test_unknown_when_no_snow_station():
    line = run(precip=(rain(0.0),))
    assert line.status == "unknown"
    assert any("SNOTEL" in m.what for m in line.missing)
    assert [c.kind for c in line.context] == ["precip"]


def test_stale_snotel_counts_as_missing():
    line = run(snow=(snow(7800, 0, days_ago=5),), precip=(rain(0.0),))
    assert line.status == "unknown"


def test_far_station_ignored():
    line = run(snow=(snow(7800, 0, km_north=80),), precip=(rain(0.0),))
    assert line.status == "unknown"


def test_station_outside_elevation_band_ignored():
    line = run(snow=(snow(4000, 0),), precip=(rain(0.0),))
    assert line.status == "unknown"


def test_patchy_precip_counts_as_missing():
    line = run(snow=(snow(7800, 0),), precip=(rain(0.0, "NWS", reported=20, expected=48),))
    assert line.status == "unknown"
    assert any("precipitation" in m.what for m in line.missing)


def test_old_nws_window_counts_as_missing():
    line = run(snow=(snow(7800, 0),), precip=(rain(0.0, "NWS", 48, 48, hours_ago=12),))
    assert line.status == "unknown"


def cond(text, hint, days_ago=1, segment="Test Segment"):
    return ConditionsObs(
        **CITE,
        segment=segment,
        text=text,
        last_updated=TODAY - dt.timedelta(days=days_ago),
        hint=hint,
    )


def test_fresh_conditions_page_muddy():
    line = run(snow=(snow(7800, 0),), precip=(rain(0.0),), conditions=(cond("Muddy", "muddy"),))
    assert line.status == "muddy"
    assert line.claims[0].kind == "conditions"


def test_stale_conditions_page_is_missing_not_used():
    line = run(conditions=(cond("Snow on trail", "snow", days_ago=60),))
    assert line.status == "unknown"
    assert any("last updated" in m.what for m in line.missing)


def test_source_gap_is_reported():
    gap = Gap(source="usfs", what="LTBMU alerts page unavailable", tried_url="https://x.gov/a")
    line = run(snow=(snow(7800, 0),), precip=(rain(0.0),), gaps=(gap,))
    assert line.status == "dry"
    assert line.missing[0].what == "LTBMU alerts page unavailable"


# The type wall: an uncited or unexplained line cannot be constructed.


def test_line_without_claims_cannot_say_dry():
    with pytest.raises(ValidationError):
        TrailLine(trail_id="x", trail_name="X", date=TODAY, status="dry")


def test_unknown_must_say_what_is_missing():
    with pytest.raises(ValidationError):
        TrailLine(trail_id="x", trail_name="X", date=TODAY, status="unknown")
    TrailLine(
        trail_id="x",
        trail_name="X",
        date=TODAY,
        status="unknown",
        missing=(Missing(what="no data", tried_url="https://example.gov"),),
    )


@pytest.mark.parametrize(
    "bad",
    [
        {"source_url": ""},
        {"source_url": "not a url"},
        {"fetched_at": dt.datetime(2026, 10, 17, 12, 0)},  # naive time
        {"quote": ""},
        {"statement": ""},
    ],
)
def test_claim_requires_citation(bad):
    fields = dict(kind="snow", statement="s", **CITE) | bad
    with pytest.raises(ValidationError):
        Claim(**fields)
