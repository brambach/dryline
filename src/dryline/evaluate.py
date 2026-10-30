"""Score hand labels (date, trail, truth) against the lines dryline published that day."""

from __future__ import annotations

import csv
import datetime as dt
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from dryline.models import STATUSES, TrailLine

TRUTHS = ("dry", "muddy", "snow", "closed")
FIELDS = ("date", "trail", "truth", "note")


@dataclass
class Label:
    date: dt.date
    trail: str
    truth: str
    note: str = ""


@dataclass
class Report:
    n: int = 0
    no_prediction: int = 0
    pairs: list[tuple[str, str]] = field(default_factory=list)  # (truth, predicted)

    @property
    def unknown_rate(self) -> float:
        return sum(p == "unknown" for _, p in self.pairs) / len(self.pairs) if self.pairs else 0.0

    def per_class(self) -> dict[str, tuple[int, int]]:
        """truth class -> (correct, total)."""
        out: dict[str, list[int]] = defaultdict(lambda: [0, 0])
        for truth, pred in self.pairs:
            out[truth][1] += 1
            out[truth][0] += truth == pred
        return {k: (v[0], v[1]) for k, v in sorted(out.items())}

    def committed_accuracy(self) -> tuple[int, int]:
        """Accuracy over the trail-days where dryline did not say unknown."""
        committed = [(t, p) for t, p in self.pairs if p != "unknown"]
        return sum(t == p for t, p in committed), len(committed)

    def confusion(self) -> Counter:
        return Counter(self.pairs)

    def render(self) -> str:
        rows = [
            f"labels: {self.n}   scored: {len(self.pairs)}   no prediction: {self.no_prediction}"
        ]
        rows.append("")
        rows.append(f"{'truth':<8} {'correct':>8} {'total':>6} {'accuracy':>9}")
        for cls, (ok, total) in self.per_class().items():
            rows.append(f"{cls:<8} {ok:>8} {total:>6} {ok / total:>9.0%}")
        ok, total = self.committed_accuracy()
        rows.append("")
        rows.append(f"unknown rate: {self.unknown_rate:.0%}")
        if total:
            rows.append(f"accuracy when not unknown: {ok}/{total} = {ok / total:.0%}")
        rows.append("")
        header = "truth \\ predicted"
        rows.append(f"{header:<18}" + "".join(f"{s:>9}" for s in STATUSES))
        conf = self.confusion()
        for t in TRUTHS:
            if any(tt == t for tt, _ in self.pairs):
                rows.append(f"{t:<18}" + "".join(f"{conf[(t, s)]:>9}" for s in STATUSES))
        return "\n".join(rows)


def read_labels(path: Path) -> list[Label]:
    labels = []
    with path.open(newline="") as f:
        for i, row in enumerate(csv.DictReader(f), start=2):
            truth = row["truth"].strip().lower()
            if truth not in TRUTHS:
                raise ValueError(f"{path}:{i}: truth {truth!r} must be one of {TRUTHS}")
            labels.append(
                Label(
                    date=dt.date.fromisoformat(row["date"].strip()),
                    trail=row["trail"].strip(),
                    truth=truth,
                    note=(row.get("note") or "").strip(),
                )
            )
    return labels


def write_label(path: Path, label: Label) -> None:
    """Insert or replace the label for (date, trail)."""
    existing = read_labels(path) if path.exists() else []
    kept = [lab for lab in existing if (lab.date, lab.trail) != (label.date, label.trail)]
    kept.append(label)
    kept.sort(key=lambda lab: (lab.date, lab.trail))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(FIELDS)
        for lab in kept:
            w.writerow([lab.date.isoformat(), lab.trail, lab.truth, lab.note])


def score(labels: list[Label], days: dict[dt.date, list[TrailLine]]) -> Report:
    report = Report(n=len(labels))
    for lab in labels:
        line = next((x for x in days.get(lab.date, []) if x.trail_id == lab.trail), None)
        if line is None:
            report.no_prediction += 1
            continue
        report.pairs.append((lab.truth, line.status))
    return report


# --- Forecast backtest -----------------------------------------------------------------------

CALLED = ("dry", "muddy", "snow")


@dataclass
class Backtest:
    """Forecast calls scored against the rules' call on the day they were for.

    This checks the forecast against dryline's own morning reading, not against riders. It says
    whether the drying math tracks the data, which is the first thing to get right.
    """

    by_lead: dict[int, list[tuple[str, str]]] = field(default_factory=lambda: defaultdict(list))

    def add(self, lead: int, predicted: str, actual: str) -> None:
        self.by_lead[lead].append((predicted, actual))

    def hits(self, lead: int | None = None) -> tuple[int, int]:
        pairs = (
            self.by_lead.get(lead, [])
            if lead is not None
            else [p for v in self.by_lead.values() for p in v]
        )
        return sum(p == a for p, a in pairs), len(pairs)

    def rows(self) -> list[tuple[int, int, int]]:
        return [(lead, *self.hits(lead)) for lead in sorted(self.by_lead)]


def backtest(outlooks, days: dict[dt.date, list[TrailLine]]) -> Backtest:
    """`outlooks`: issued date -> DayOutlook (dryline.pipeline)."""
    bt = Backtest()
    actual = {(d, line.trail_id): line.status for d, lines in days.items() for line in lines}
    for issued, day_outlook in sorted(outlooks.items()):
        for o in day_outlook.trails:
            for od in o.days[1:]:
                truth = actual.get((od.date, o.trail_id))
                if od.status in CALLED and truth in CALLED:
                    bt.add((od.date - issued).days, od.status, truth)
    return bt
