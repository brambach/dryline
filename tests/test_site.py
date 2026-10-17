import datetime as dt

import feedparser
import pytest
from selectolax.lexbor import LexborHTMLParser as HTMLParser
from test_rules import TRAIL

from dryline.models import Claim, Missing, TrailLine
from dryline.site import UncitedLine, build_site, check_every_line_linked, load_lines, save_lines

DAY = dt.date(2026, 10, 17)
BUILT = dt.datetime(2026, 10, 17, 13, 10, tzinfo=dt.UTC)
FETCHED = dt.datetime(2026, 10, 17, 13, 2, tzinfo=dt.UTC)


def claim(
    kind="snow", statement="Snow likely above ~7,500 ft.", url="https://wcc.sc.egov.usda.gov/x"
):
    return Claim(
        kind=kind,
        statement=statement,
        source_name="SNOTEL",
        source_url=url,
        fetched_at=FETCHED,
        quote="SNWD=6",
    )


def lines_for(day):
    return [
        TrailLine(
            trail_id=TRAIL.id,
            trail_name=TRAIL.name,
            date=day,
            status="snow",
            claims=(claim(),),
            forecast=claim("forecast", "NWS Today: Sunny.", "https://api.weather.gov/f"),
        ),
        TrailLine(
            trail_id="other",
            trail_name="Other & <Trail>",
            date=day,
            status="unknown",
            missing=(
                Missing(what="No SNOTEL station nearby", tried_url="https://wcc.sc.egov.usda.gov/"),
            ),
        ),
    ]


@pytest.fixture
def site(tmp_path):
    lines_dir = tmp_path / "lines"
    save_lines(lines_dir, DAY - dt.timedelta(days=1), lines_for(DAY - dt.timedelta(days=1)))
    save_lines(lines_dir, DAY, lines_for(DAY))
    days = load_lines(lines_dir)
    out = tmp_path / "site"
    build_site(out, days, [TRAIL], BUILT)
    return out


def test_builds_all_pages(site):
    for rel in [
        "index.html",
        "today.json",
        "feed.xml",
        "style.css",
        "archive/index.html",
        f"archive/{DAY}/index.html",
        f"archive/{DAY}.json",
        f"trails/{TRAIL.id}/index.html",
    ]:
        assert (site / rel).exists(), rel


def test_every_rendered_line_has_a_source_link(site):
    html = (site / "index.html").read_text()
    assert check_every_line_linked(html) == 2
    tree = HTMLParser(html)
    for row in tree.css("[data-line]"):
        links = [a.attributes["href"] for a in row.css("a[data-source]")]
        assert links and all(h.startswith("https://") for h in links)
    assert "Other &amp; &lt;Trail&gt;" in html  # escaped


def test_uncited_line_is_rejected():
    with pytest.raises(UncitedLine):
        check_every_line_linked('<li data-line="x">Dry, trust me. <a href="/trails/x/">x</a></li>')


def test_feed_parses(site):
    feed = feedparser.parse((site / "feed.xml").read_text())
    assert not feed.bozo, feed.bozo_exception
    assert len(feed.entries) == 2
    assert feed.entries[0].title.endswith("1 snow, 1 unknown")
    assert "https://wcc.sc.egov.usda.gov/x" in feed.entries[0].description
    assert "fetched Oct 17" in feed.entries[0].description
    assert "<![CDATA[" in (site / "feed.xml").read_text()
