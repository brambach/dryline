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
    trta_segment="TestSeg",
    status_sources=("usfs-ltbmu", "trta"),
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


def rain(total, network="SNOTEL", reported=2, expected=2, hours_ago=1, dry_capable=True):
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
        dry_capable=dry_capable,
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
    assert "No snow at similar elevation: Station 7900" in line.claims[0].statement
    assert "only above ~8,800 ft" in line.claims[1].statement


def test_snow_depth_noise_below_threshold_is_not_snow():
    line = run(snow=(snow(7800, 1),), precip=(rain(0.0),))
    assert line.status == "dry"


def test_muddy_after_rain():
    line = run(snow=(snow(7800, 0),), precip=(rain(0.6),))
    assert line.status == "muddy"
    assert "0.60 in" in line.claims[0].statement


def test_closed_beats_everything():
    closure = ClosureObs(
        **CITE, page="usfs-ltbmu", title="Test Trail Closure Order", link="https://example.gov/a/1"
    )
    line = run(snow=(snow(7500, 6),), precip=(rain(1.0),), closures=(closure,))
    assert line.status == "closed"
    assert {c.kind for c in line.context} == {"snow", "precip"}


def test_unrelated_closure_ignored():
    other = ClosureObs(
        **CITE, page="usfs-ltbmu", title="Other Road Closure", link="https://example.gov/a/2"
    )
    # Right name, but posted by a forest that doesn't manage this trail.
    elsewhere = ClosureObs(
        **CITE, page="usfs-tnf", title="Test Trail Closure", link="https://example.gov/a/3"
    )
    line = run(snow=(snow(7800, 0),), precip=(rain(0.0),), closures=(other, elsewhere))
    assert line.status == "dry"


def test_closure_keyword_in_summary():
    closure = ClosureObs(
        **CITE,
        page="usfs-ltbmu",
        title="Area Closure Order",
        summary="Closes the Test Trail and nearby roads.",
        link="https://example.gov/a/4",
    )
    assert run(closures=(closure,)).status == "closed"


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


def cond(text, hint, days_ago=1, segment="TestSeg"):
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


def test_snow_free_conditions_entry_is_not_dry_without_rain_data():
    line = run(conditions=(cond("Clear of snow", "snow_free"),))
    assert line.status == "unknown"
    assert line.context[0].kind == "conditions"


def test_source_gap_is_reported():
    gap = Gap(
        source="usfs-ltbmu", what="LTBMU alerts page unavailable", tried_url="https://x.gov/a"
    )
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


def test_gap_for_unrelated_source_not_shown():
    gap = Gap(source="usfs-htnf", what="HTNF alerts unavailable", tried_url="https://x.gov/b")
    line = run(snow=(snow(7800, 0),), precip=(rain(0.0),), gaps=(gap,))
    assert line.missing == ()


def test_snow_free_witness_prefers_near_station_above_high_point():
    near = snow(8100, 0, km_north=3, sid="near")
    far = snow(8900, 0, km_north=35, sid="far")
    below = snow(7600, 0, km_north=1, sid="below")
    line = run(snow=(far, near, below), precip=(rain(0.0),))
    assert line.status == "dry"
    assert "Station 8100" in line.claims[0].statement


# Regressions from review.


def test_snow_just_above_high_point_without_bare_witness_is_unknown():
    assert run(snow=(snow(8100, 12),), precip=(rain(0.0),)).status == "unknown"
    line = run(snow=(snow(5600, 0), snow(8900, 20)), precip=(rain(0.0),))
    assert line.status == "unknown"
    assert any("bare ground" in m.what for m in line.missing)


def test_snotel_precip_window_must_be_recent():
    assert run(snow=(snow(7800, 0),), precip=(rain(0.0, hours_ago=40),)).status == "unknown"
    assert run(snow=(snow(7800, 0),), precip=(rain(0.0, hours_ago=20),)).status == "dry"


def test_precip_statement_names_the_window():
    line = run(snow=(snow(7800, 0),), precip=(rain(0.0),))
    assert "on Oct 15–17" in line.claims[1].statement or "on Oct" in line.claims[1].statement


def test_rain_counts_even_from_patchy_or_non_asos_gauge():
    line = run(snow=(snow(7800, 0),), precip=(rain(0.5, "NWS", 10, 48, dry_capable=False),))
    assert line.status == "muddy"


def test_non_asos_zero_is_not_dry_evidence():
    line = run(snow=(snow(7800, 0),), precip=(rain(0.0, "NWS", 48, 48, dry_capable=False),))
    assert line.status == "unknown"


def test_future_closure_not_in_effect():
    closure = ClosureObs(
        **CITE,
        page="usfs-ltbmu",
        title="Test Trail Closure",
        link="https://example.gov/a/9",
        published=TODAY + dt.timedelta(days=3),
    )
    assert run(snow=(snow(7800, 0),), precip=(rain(0.0),), closures=(closure,)).status == "dry"


def test_missing_trta_segment_is_reported():
    other = cond("Free of snow", "snow_free", segment="SomethingElse")
    line = run(snow=(snow(7800, 0),), precip=(rain(0.0),), conditions=(other,))
    assert any("TestSeg not found" in m.what for m in line.missing)


def test_trta_snow_free_alone_is_not_enough_for_dry():
    line = run(precip=(rain(0.0),), conditions=(cond("Free of snow", "snow_free"),))
    assert line.status == "unknown"


def test_digest_date_comes_from_day_not_now():
    line = evaluate(TRAIL, Observations(), NOW + dt.timedelta(days=1), today=TODAY)
    assert line.date == TODAY
