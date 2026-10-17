"""Build today's page from recorded fixtures with the real trails, stations, and NWS grid."""

import datetime as dt
import shutil
from pathlib import Path

import pytest

from dryline.config import load_grid, load_stations, load_trails
from dryline.fetch import raw_path
from dryline.pipeline import lines_for_day
from dryline.site import build_site, check_every_line_linked

ROOT = Path(__file__).parent.parent
FIX = ROOT / "tests" / "fixtures"
DAY = dt.date(2026, 10, 16)
NOW = dt.datetime(2026, 10, 17, 6, 30, tzinfo=dt.UTC)  # 11:30pm Pacific on Oct 16


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("e2e")
    raw = tmp / "raw"
    placed = {
        ("snotel", "daily"): "snotel-prcp",
        ("nws", "obs-KTVL"): "nws-obs-KTVL",
        ("pages", "trta"): "trta",
        ("pages", "usfs-ltbmu"): "usfs-ltbmu",
        ("pages", "usfs-tnf"): "usfs-tnf",
        ("pages", "nvparks-tahoe"): "nvparks-tahoe",
        # usfs-htnf deliberately absent: Mount Rose must show the gap
    }
    for (source, name), fixture in placed.items():
        dest = raw_path(raw, DAY, source, name)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(FIX / f"{fixture}.json.gz", dest)
    trails = load_trails(ROOT / "trails.yaml")
    lines = lines_for_day(
        raw,
        DAY,
        trails,
        load_stations(ROOT / "stations.yaml"),
        load_grid(ROOT / "nws_grid.yaml"),
        NOW,
    )
    out = tmp / "site"
    build_site(out, {DAY: lines}, trails, NOW)
    return lines, out


def test_one_line_per_trail(built):
    lines, _ = built
    assert len(lines) == 20
    assert {line.status for line in lines} <= {"dry", "unknown"}


def test_every_page_every_line_linked(built):
    _, out = built
    pages = [
        out / "index.html",
        *out.glob("archive/*/index.html"),
        *out.glob("trails/*/index.html"),
    ]
    assert len(pages) == 22
    total = sum(check_every_line_linked(p.read_text()) for p in pages)
    assert total == 20 * 2 + 20  # today + archive day, plus one block per trail page


def test_missing_source_shows_up(built):
    lines, _ = built
    rose = next(line for line in lines if line.trail_id == "mount-rose-summit")
    assert any("Humboldt-Toiyabe" in m.what and "not fetched" in m.what for m in rose.missing)
    rubicon = next(line for line in lines if line.trail_id == "rubicon-trail-dl-bliss")
    assert any("No official closure source" in m.what for m in rubicon.missing)


def test_renderer_rejects_non_lines(tmp_path):
    with pytest.raises(TypeError):
        build_site(tmp_path / "s", {DAY: [{"status": "dry", "trail_name": "x"}]}, [], NOW)
