from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from dryline.config import load_trails
from dryline.models import Trail

ROOT = Path(__file__).parent.parent
if not (ROOT / "trails.yaml").exists():
    pytest.skip("trails.yaml not drafted yet", allow_module_level=True)
TRTA_SEGMENTS = {
    "TCtoBrockway",
    "BrockwaytoRose",
    "TMtoSpooner",
    "SpoonertoKBN",
    "KBNtoKBS",
    "KBStoBM",
    "BMtoEcho",
    "EchotoBP",
    "BPtoTC",
}


@pytest.fixture(scope="module")
def trails():
    return load_trails(ROOT / "trails.yaml")


def test_twenty_trails(trails):
    assert len(trails) == 20


def test_every_trail_cites_a_source_and_sits_in_tahoe(trails):
    for t in trails:
        assert t.sources, t.id
        assert all(str(s).startswith("https://") for s in t.sources), t.id
        assert t.trailhead.in_tahoe(), t.id
        assert t.high_point is None or t.high_point.in_tahoe(), t.id


def test_trta_segments_exist(trails):
    for t in trails:
        assert t.trta_segment is None or t.trta_segment in TRTA_SEGMENTS, t.id


def test_all_await_review(trails):
    assert not any(t.confirmed for t in trails)


def raw_trail(**over):
    data = yaml.safe_load((ROOT / "trails.yaml").read_text())["trails"][0]
    return data | over


def test_schema_rejects_missing_sources():
    with pytest.raises(ValidationError):
        Trail.model_validate(raw_trail(sources=[]))
    data = raw_trail()
    del data["sources"]
    with pytest.raises(ValidationError):
        Trail.model_validate(data)


@pytest.mark.parametrize(
    "point",
    [{"lat": 37.75, "lon": -119.59}, {"lat": 39.0, "lon": -121.0}, {"lat": 39.53, "lon": -119.81}],
)
def test_schema_rejects_points_outside_tahoe(point):
    # Yosemite Valley, Auburn-ish longitude, Reno
    with pytest.raises(ValidationError, match="outside the Tahoe bounding box"):
        Trail.model_validate(raw_trail(trailhead=point))
