import datetime as dt
import json
from pathlib import Path

import pytest

from dryline.config import ObsStation, load_stations
from dryline.fetch import load_raw
from dryline.obs import Observations
from dryline.parse import (
    ParseError,
    conditions_hint,
    parse_nws_forecast,
    parse_nws_observations,
    parse_snotel,
    parse_trta,
    parse_usfs_alerts,
)
from dryline.rules import evaluate

FIX = Path(__file__).parent / "fixtures"
ROOT = Path(__file__).parent.parent
RECORDED = dt.datetime(2026, 10, 17, 5, 30, tzinfo=dt.UTC)
KTVL = ObsStation(id="KTVL", name="South Lake Tahoe Airport", lat=38.89, lon=-119.99)


def fixture(name):
    return load_raw(FIX / f"{name}.json.gz")


def changed(raw, **replacements):
    body = raw.body
    for old, new in replacements.items():
        assert old in body
        body = body.replace(old, new)
    return raw.model_copy(update={"body": body})


# --- SNOTEL ---


def test_snotel_parses_depth_for_every_station():
    stations = {s.triplet: s for s in load_stations(ROOT / "stations.yaml").snotel}
    snow, precip = parse_snotel(fixture("snotel"), stations)
    assert {o.station_id for o in snow} == set(stations)
    assert max(o.date for o in snow) == dt.date(2026, 10, 15)
    rose = [o for o in snow if o.station_name == "Mt Rose Ski Area" and o.date.day == 12][0]
    assert rose.depth_in == 1 and "SNWD=1 in, WTEQ=0.1 in" in rose.quote
    assert precip == []  # this recording didn't request PRCP


def test_snotel_prcp_window():
    stations = {s.triplet: s for s in load_stations(ROOT / "stations.yaml").snotel}
    body = [
        {
            "stationTriplet": "809:CA:SNTL",
            "data": [
                {
                    "stationElement": {"elementCode": "PRCP"},
                    "values": [
                        {"date": "2026-10-14", "value": 0.4},
                        {"date": "2026-10-15", "value": 0.2},
                        {"date": "2026-10-16", "value": 0.1},
                    ],
                }
            ],
        }
    ]
    raw = fixture("snotel").model_copy(update={"body": json.dumps(body)})
    _, precip = parse_snotel(raw, stations)
    (p,) = precip
    assert p.total_in == pytest.approx(0.3)
    assert p.periods_reported == 2
    assert p.window_end.date() == dt.date(2026, 10, 17)


def test_snotel_error_shape_raises():
    raw = fixture("snotel").model_copy(update={"body": '{"error": "bad"}'})
    with pytest.raises(ParseError):
        parse_snotel(raw, {})


# --- NWS ---


def test_nws_obs_counts_metar_hours():
    p = parse_nws_observations(fixture("nws-obs-KTVL"), KTVL, RECORDED, asos=True)
    assert p.dry_capable
    assert p.total_in == 0.0
    assert p.periods_reported == 34 and p.periods_expected == 48
    assert "precipitation groups: none" in p.quote


def test_nws_obs_sums_p_groups_and_skips_pno():
    def feat(ts, msg):
        return {"properties": {"timestamp": ts, "rawMessage": msg}}

    body = {
        "features": [
            feat("2026-10-17T04:53:00+00:00", "KTVL 170453Z AUTO RA RMK AO2 P0012 T00331056"),
            feat("2026-10-17T03:53:00+00:00", "KTVL 170353Z AUTO RA RMK AO2 P0030"),
            feat("2026-10-17T02:53:00+00:00", "KTVL 170253Z AUTO RMK AO2 PNO"),
            feat("2026-10-17T01:53:00+00:00", "KTVL 170153Z AUTO RMK AO2"),
        ]
    }
    raw = fixture("nws-obs-KTVL").model_copy(update={"body": json.dumps(body)})
    p = parse_nws_observations(raw, KTVL, RECORDED, asos=True)
    assert p.total_in == pytest.approx(0.42)
    assert p.periods_reported == 3  # the PNO hour is not counted as dry


def _obs_raw(*feats):
    body = {"features": [{"properties": {"timestamp": t, "rawMessage": m}} for t, m in feats]}
    return fixture("nws-obs-KTVL").model_copy(update={"body": json.dumps(body)})


def test_nws_speci_after_routine_does_not_replace_hour():
    raw = _obs_raw(
        ("2026-10-17T04:58:00+00:00", "KTVL 170458Z AUTO RA RMK AO2 P0001"),
        ("2026-10-17T04:53:00+00:00", "KTVL 170453Z AUTO RA RMK AO2 P0010"),
    )
    assert parse_nws_observations(raw, KTVL, RECORDED, asos=True).total_in == pytest.approx(0.10)


def test_nws_window_ends_at_last_counted_report():
    raw = _obs_raw(
        ("2026-10-17T04:53:00+00:00", "KTVL 170453Z AUTO +RA RMK AO2 PNO"),
        ("2026-10-16T20:53:00+00:00", "KTVL 162053Z AUTO RMK AO2"),
    )
    p = parse_nws_observations(raw, KTVL, RECORDED, asos=True)
    assert p.window_end == dt.datetime(2026, 10, 16, 20, 53, tzinfo=dt.UTC)


def test_nws_off_hour_awos_reports_ignored():
    raw = _obs_raw(("2026-10-17T04:15:00+00:00", "KTRK 170415Z AUTO RMK AO2"))
    with pytest.raises(ParseError):
        parse_nws_observations(raw, KTVL, RECORDED)


def test_nws_forecast_current_period():
    f = parse_nws_forecast(fixture("nws-forecast"), RECORDED)
    assert f.period == "Tonight"
    assert f.short_forecast.startswith("Mostly Clear")


def test_nws_forecast_stale_raises():
    with pytest.raises(ParseError):
        parse_nws_forecast(fixture("nws-forecast"), RECORDED + dt.timedelta(days=2))


# --- TRTA conditions page ---


def test_trta_segments_and_dates():
    obs, gaps = parse_trta(fixture("trta"))
    assert gaps == []
    by_seg = {o.segment: o for o in obs}
    assert len(by_seg) == 9
    assert by_seg["TCtoBrockway"].last_updated == dt.date(2026, 6, 24)
    assert by_seg["TCtoBrockway"].hint == "snow_free"
    assert by_seg["BMtoEcho"].hint is None


def test_trta_august_page_is_stale_on_october_17():
    from test_rules import TRAIL

    trail = TRAIL.model_copy(update={"trta_segment": "TCtoBrockway"})
    obs, _ = parse_trta(fixture("trta"))
    line = evaluate(trail, Observations(conditions=tuple(obs)), RECORDED)
    assert line.status == "unknown"
    assert any("Jun 24" in m.what and "older than" in m.what for m in line.missing)


def test_trta_changed_layout_yields_unknown_not_a_guess():
    from test_rules import TRAIL, rain, snow

    raw = changed(fixture("trta"), **{"vc_row": "segment-row"})
    obs, gaps = parse_trta(raw)
    assert obs == []
    assert gaps and "layout not recognized" in gaps[0].what
    trail = TRAIL.model_copy(update={"trta_segment": "TCtoBrockway"})
    line = evaluate(trail, Observations(gaps=tuple(gaps)), RECORDED)
    assert line.status == "unknown"
    assert any("layout not recognized" in m.what for m in line.missing)
    # Even with good weather data, the gap stays visible as a caveat.
    line = evaluate(
        trail, Observations(snow=(snow(7800, 0),), precip=(rain(0.0),), gaps=tuple(gaps)), RECORDED
    )
    assert any("layout not recognized" in m.what for m in line.missing)


def test_trta_date_format_change_is_reported():
    raw = changed(fixture("trta"), **{"Last Updated": "Revised"})
    obs, gaps = parse_trta(raw)
    assert obs == [] and gaps


# --- USFS alerts ---


def test_usfs_closures_only():
    obs, gaps = parse_usfs_alerts(fixture("usfs-ltbmu"), "usfs-ltbmu")
    assert gaps == []
    assert [o.title for o in obs] == ["Meyers Landfill Area Closure"]
    assert obs[0].published == dt.date(2025, 4, 9)
    assert str(obs[0].link).startswith("https://www.fs.usda.gov/r05/laketahoebasin/alerts/")
    tnf, _ = parse_usfs_alerts(fixture("usfs-tnf"), "usfs-tnf")
    assert "Signal Peak Trail Closure" in [o.title for o in tnf]


def test_usfs_changed_layout_is_a_gap():
    raw = changed(fixture("usfs-ltbmu"), **{"rows__container": "alerts-list"})
    obs, gaps = parse_usfs_alerts(raw, "usfs-ltbmu")
    assert obs == [] and "layout not recognized" in gaps[0].what


def test_http_error_is_a_gap():
    raw = fixture("usfs-ltbmu").model_copy(update={"status_code": 503})
    obs, gaps = parse_usfs_alerts(raw, "usfs-ltbmu")
    assert obs == [] and "HTTP 503" in gaps[0].what


@pytest.mark.parametrize(
    "text,hint",
    [
        ("This section is now completely free of snow!", "snow_free"),
        ("Trail is snow-free but muddy near the creek.", "muddy"),
        ("Patchy snow above 8,500 ft; otherwise clear of snow.", "snow"),
        ("Trail closed for construction.", "closed"),
        ("Expect mosquitos.", None),
        ("No closures on this section; trail is free of snow.", "snow_free"),
        ("No mud, free of snow.", "snow_free"),
        ("Reopened after the closure.", None),
        ("Trail closed for construction. No snow.", "closed"),
    ],
)
def test_conditions_hint(text, hint):
    assert conditions_hint(text) == hint


def test_snotel_live_recording_with_prcp():
    """Recorded by the first live run (2026-10-16 22:40 PT): SNWD, WTEQ, PRCP for 24 stations."""
    stations = {s.triplet: s for s in load_stations(ROOT / "stations.yaml").snotel}
    raw = fixture("snotel-prcp")
    assert "elements=SNWD%2CWTEQ%2CPRCP" in raw.url
    snow, precip = parse_snotel(raw, stations)
    assert len(precip) == 24
    assert all(p.periods_reported == 2 and p.total_in == 0 for p in precip)
    assert max(o.date for o in snow) == dt.date(2026, 10, 15)


def test_nvparks_banner_without_closure():
    from dryline.parse import parse_nvparks

    obs, gaps = parse_nvparks(fixture("nvparks-tahoe"))
    assert obs == [] and gaps == []


def test_nvparks_closure_banner_and_changed_layout():
    from dryline.parse import parse_nvparks

    raw = fixture("nvparks-tahoe")
    banner = (
        '<ul id="alert"><li><h3>Spooner Lake Backcountry Closed</h3>'
        "<p>Marlette Lake trail closed for construction.</p></li></ul>"
    )
    obs, _ = parse_nvparks(
        raw.model_copy(update={"body": raw.body.replace("<body", banner + "<body", 1)})
    )
    assert [o.title for o in obs] == ["Spooner Lake Backcountry Closed"]
    rel = (
        '<ul id="alert"><li><h3>Marlette Trail Closed</h3><p>Closed.</p>'
        '<a class="read-more" href="/parks/lake-tahoe/alerts/1">More</a></li></ul>'
    )
    obs, _ = parse_nvparks(
        raw.model_copy(update={"body": raw.body.replace('<ul id="alert">', rel + '<ul id="x">', 1)})
    )
    assert str(obs[0].link) == "https://parks.nv.gov/parks/lake-tahoe/alerts/1"
    no_banner = raw.model_copy(update={"body": raw.body.replace('id="alert"', 'id="banner"')})
    obs, gaps = parse_nvparks(no_banner)
    assert obs == [] and "banner not found" in gaps[0].what
    no_title = raw.model_copy(update={"body": raw.body.replace("Lake Tahoe", "Somewhere")})
    obs, gaps = parse_nvparks(no_title)
    assert obs == [] and "layout not recognized" in gaps[0].what
