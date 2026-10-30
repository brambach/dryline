"""The ridge: the basin drawn as one ink engraving, every trail at its real high point.

Pure geometry, no randomness at render time. The skyline between trails is made up (seeded
midpoint displacement) and says so in the figure's caption; the trails' heights, the snow
line and the lake are real numbers.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

from dryline.forecast import BASIN_CENTER, LAKE_FT
from dryline.models import Trail

W, H = 1200, 440
TOP_FT, BOTTOM_FT = 11200, 5900
Y_TOP, Y_BOTTOM = 34, 408
PAD = 64

SHORT = {
    "tahoe rim trail: brockway summit to martis peak": "Martis Peak",
    "big meadow to round lake": "Round Lake",
    "echo lakes to lake aloha": "Lake Aloha",
    "van sickle trail": "Van Sickle",
    "marlette lake": "Marlette Lake",
    "mount judah loop": "Mount Judah",
}


def short_name(trail: Trail) -> str:
    base = trail.name.split(" (")[0].split(" via ")[0].strip()
    return SHORT.get(base.lower(), base)


def y_of(ft: float) -> float:
    return Y_BOTTOM - (ft - BOTTOM_FT) * (Y_BOTTOM - Y_TOP) / (TOP_FT - BOTTOM_FT)


def bearing(trail: Trail) -> float:
    """Clockwise degrees from north, seen from the middle of the lake."""
    p = trail.high_point or trail.trailhead
    dy = p.lat - BASIN_CENTER.lat
    dx = (p.lon - BASIN_CENTER.lon) * math.cos(math.radians(BASIN_CENTER.lat))
    return (math.degrees(math.atan2(dx, dy)) + 360) % 360


@dataclass(frozen=True)
class Marker:
    trail_id: str
    name: str
    short: str
    x: float
    y: float  # the high point on the ridge
    top_ft: int
    bottom_ft: int


@dataclass(frozen=True)
class Ridge:
    width: int
    height: int
    path: str  # closed silhouette down to the lake
    line: str  # the ridge's top edge only
    far: str  # a lighter range behind
    facets: tuple[str, ...]  # shaded slopes (facing away from the light)
    markers: tuple[Marker, ...]
    lake_y: float
    lake_lines: tuple[tuple[float, float, float], ...]  # x1, x2, y
    contours: tuple[float, ...]  # downward offsets for the engraved copies of the crest
    ticks: tuple[tuple[int, float], ...]  # elevation, y


def _displace(a, b, depth, rng, rough):
    """Midpoint displacement between two skyline points."""
    if depth == 0 or b[0] - a[0] < 10:
        return [a]
    mx = (a[0] + b[0]) / 2
    my = (a[1] + b[1]) / 2 + rng.uniform(-1, 1) * rough * (b[0] - a[0])
    m = (mx, my)
    return _displace(a, m, depth - 1, rng, rough * 0.6) + _displace(
        m, b, depth - 1, rng, rough * 0.6
    )


def build_ridge(trails: list[Trail]) -> Ridge:
    rng = random.Random(6225)
    ordered = sorted(trails, key=bearing)
    n = len(ordered)
    step = (W - 2 * PAD) / max(n - 1, 1)
    markers = tuple(
        Marker(
            trail_id=t.id,
            name=t.name,
            short=short_name(t),
            x=round(PAD + i * step, 1),
            y=round(y_of(t.elevation_max_ft), 1),
            top_ft=t.elevation_max_ft,
            bottom_ft=t.elevation_min_ft,
        )
        for i, t in enumerate(ordered)
    )
    lake_y = y_of(LAKE_FT)
    # Peaks at each trail's high point, saddles between them a little lower than the lower peak.
    anchors = [(0.0, y_of(6900))]
    for i, m in enumerate(markers):
        anchors.append((m.x, m.y))
        if i + 1 < n:
            nxt = markers[i + 1]
            low = max(m.y, nxt.y)
            sag = rng.uniform(10, 26)
            anchors.append(((m.x + nxt.x) / 2 + rng.uniform(-8, 8), min(low + sag, lake_y - 30)))
    anchors.append((float(W), y_of(7100)))
    # Flanks steepen toward the summit and flatten into the saddles, like real ridges.
    shaped: list[tuple[float, float]] = []
    for a, b in zip(anchors, anchors[1:], strict=False):
        shaped.append(a)
        hi, lo = (a, b) if a[1] < b[1] else (b, a)
        for t in (0.25, 0.5, 0.75):
            x = a[0] + (b[0] - a[0]) * t
            u = abs(x - hi[0]) / abs(lo[0] - hi[0]) if lo[0] != hi[0] else 0
            shaped.append((x, hi[1] + (lo[1] - hi[1]) * u**0.7))
    shaped.append(anchors[-1])
    pts: list[tuple[float, float]] = []
    for a, b in zip(shaped, shaped[1:], strict=False):
        pts += _displace(a, b, 3, rng, 0.3)
    pts.append(anchors[-1])
    # Keep the real peaks on top: nothing between two trails rises above the higher of them.
    marks_x = [m.x for m in markers]
    capped = []
    for x, y in pts:
        i = next((k for k, mx in enumerate(marks_x) if mx >= x), len(marks_x) - 1)
        neighbours = [markers[j].y for j in (i - 1, i) if 0 <= j < n]
        if all(abs(x - mx) > 0.5 for mx in marks_x):
            y = max(y, min(neighbours) + 6)
        capped.append((x, y))
    pts = capped
    line = "M" + " L".join(f"{x:.1f} {y:.1f}" for x, y in pts)
    path = line + f" L{W} {lake_y:.1f} L0 {lake_y:.1f} Z"

    far_rng = random.Random(1849)
    far_pts = [(0.0, y_of(8600))]
    for x in range(100, W + 1, 100):
        far_pts.append((float(x), y_of(far_rng.uniform(8300, 9900))))
    fp: list[tuple[float, float]] = []
    for a, b in zip(far_pts, far_pts[1:], strict=False):
        fp += _displace(a, b, 4, far_rng, 0.12)
    fp.append(far_pts[-1])
    far = (
        "M" + " L".join(f"{x:.1f} {y:.1f}" for x, y in fp) + f" L{W} {lake_y:.1f} L0 {lake_y:.1f} Z"
    )

    # Light from the upper left: slopes that fall to the right sit in shade.
    facets = []
    run: list[tuple[float, float]] = []
    for p, q in zip(pts, pts[1:], strict=False):
        if q[1] > p[1] + 0.5:
            run = run or [p]
            run.append(q)
        elif run:
            facets.append(_facet(run, lake_y))
            run = []
    if run:
        facets.append(_facet(run, lake_y))

    lake_lines = []
    lrng = random.Random(39)
    y = lake_y + 5
    gap = 4.0
    while y < H - 2:
        x = lrng.uniform(-40, 30)
        while x < W:
            length = lrng.uniform(60, 260)
            lake_lines.append((round(max(x, 0), 1), round(min(x + length, W), 1), round(y, 1)))
            x += length + lrng.uniform(10, 50)
        y += gap
        gap *= 1.18
    contours, off, gap = [], 2.6, 2.6
    while off < lake_y - Y_TOP:
        contours.append(round(off, 2))
        gap = min(gap * 1.045, 7.5)
        off += gap
    ticks = tuple((ft, round(y_of(ft), 1)) for ft in (7000, 8000, 9000, 10000, 11000))
    return Ridge(
        width=W,
        height=H,
        path=path,
        line=line,
        far=far,
        facets=tuple(facets),
        markers=markers,
        lake_y=round(lake_y, 1),
        lake_lines=tuple(lake_lines),
        contours=tuple(contours),
        ticks=ticks,
    )


def _facet(run: list[tuple[float, float]], lake_y: float) -> str:
    top = " L".join(f"{x:.1f} {y:.1f}" for x, y in run)
    drop = 70
    back = " L".join(f"{x - 14:.1f} {min(y + drop, lake_y):.1f}" for x, y in reversed(run))
    return f"M{top} L{back} Z"
