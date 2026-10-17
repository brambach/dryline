import datetime as dt

from dryline.evaluate import Label, read_labels, score, write_label
from dryline.label import render_page
from dryline.models import Claim, Missing, TrailLine

DAY = dt.date(2026, 10, 17)
CLAIM = Claim(
    kind="snow",
    statement="s",
    source_name="x",
    source_url="https://example.gov",
    fetched_at=dt.datetime(2026, 10, 17, 13, tzinfo=dt.UTC),
    quote="q",
)
GAP = Missing(what="no data", tried_url="https://example.gov")


def line(trail, status):
    if status == "unknown":
        return TrailLine(trail_id=trail, trail_name=trail, date=DAY, status=status, missing=(GAP,))
    return TrailLine(trail_id=trail, trail_name=trail, date=DAY, status=status, claims=(CLAIM,))


def test_score_per_class_and_unknown_rate():
    days = {DAY: [line("a", "dry"), line("b", "snow"), line("c", "unknown"), line("d", "dry")]}
    labels = [
        Label(DAY, "a", "dry"),
        Label(DAY, "b", "snow"),
        Label(DAY, "c", "muddy"),
        Label(DAY, "d", "muddy"),
        Label(DAY, "zzz", "dry"),  # no prediction for this trail
    ]
    r = score(labels, days)
    assert r.no_prediction == 1
    assert r.per_class() == {"dry": (1, 1), "muddy": (0, 2), "snow": (1, 1)}
    assert r.unknown_rate == 0.25
    assert r.committed_accuracy() == (2, 3)
    text = r.render()
    assert "unknown rate: 25%" in text and "muddy" in text


def test_write_label_upserts(tmp_path):
    path = tmp_path / "labels.csv"
    write_label(path, Label(DAY, "a", "dry"))
    write_label(path, Label(DAY, "b", "snow", "saw it"))
    write_label(path, Label(DAY, "a", "muddy"))
    labels = read_labels(path)
    assert [(lab.trail, lab.truth) for lab in labels] == [("a", "muddy"), ("b", "snow")]
    assert path.read_text().splitlines()[0] == "date,trail,truth,note"


def test_label_page_hides_prediction_behind_details():
    html = render_page({DAY: [line("a", "dry")]}, [Label(DAY, "a", "dry")], "labels.csv")
    assert "<details><summary>dryline said</summary>Likely dry." in html
    assert 'value="dry" checked' in html
