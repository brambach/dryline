"""Live collection. One request per URL per day; everything lands in data/raw/YYYY-MM-DD/."""

from __future__ import annotations

import datetime as dt

import yaml

from dryline.config import (
    AWDB_DATA_URL,
    NWS_API,
    PAGES,
    GridEntry,
    GridFile,
    ObsStation,
    StationsFile,
)
from dryline.fetch import Disallowed, Fetcher
from dryline.models import LatLon, Trail
from dryline.obs import km_between

GEOJSON = {"Accept": "application/geo+json"}
# api.weather.gov and the AWDB REST API are documented machine APIs. api.weather.gov's
# robots.txt disallows crawlers ("Disallow: /") to keep it out of search indexes; NWS asks API
# clients to send an identifying User-Agent instead, which we do. HTML pages always check robots.
API_SOURCES_SKIP_ROBOTS = True
SNOTEL_ELEMENTS = "SNWD,WTEQ,PRCP"
# dryline's own rider reports, archived daily so the eval can score against them.
REPORTS_URL = "https://dryline.brycerambach.com/api/reports?days=1"


def collect_snotel(f: Fetcher, stations: StationsFile, day: dt.date) -> None:
    f.get(
        "snotel",
        "daily",
        AWDB_DATA_URL,
        params={
            "stationTriplets": ",".join(s.triplet for s in stations.snotel),
            "elements": SNOTEL_ELEMENTS,
            "duration": "DAILY",
            "beginDate": (day - dt.timedelta(days=7)).isoformat(),
            "endDate": day.isoformat(),
        },
        check_robots=not API_SOURCES_SKIP_ROBOTS,
    )


def forecast_name(entry: GridEntry) -> str:
    # https://api.weather.gov/gridpoints/REV/34,81/forecast -> REV-34-81
    parts = str(entry.forecast_url).rstrip("/").split("/")
    return f"{parts[-3]}-{parts[-2].replace(',', '-')}"


def collect_nws(f: Fetcher, grid: GridFile, now: dt.datetime) -> None:
    forecasts = {forecast_name(e): str(e.forecast_url) for e in grid.trails.values()}
    for name, url in sorted(forecasts.items()):
        f.get("nws", f"forecast-{name}", url, headers=GEOJSON, check_robots=False)
    stations = {e.obs_station.id for e in grid.trails.values() if e.obs_station}
    start = (now - dt.timedelta(hours=49)).replace(microsecond=0)
    for sid in sorted(stations):
        f.get(
            "nws",
            f"obs-{sid}",
            f"{NWS_API}/stations/{sid}/observations",
            params={"start": start.isoformat().replace("+00:00", "Z")},
            headers=GEOJSON,
            check_robots=not API_SOURCES_SKIP_ROBOTS,
        )


def collect_pages(f: Fetcher, trails: list[Trail]) -> list[str]:
    """Fetch each official page that at least one trail uses. Returns skipped sources."""
    wanted = sorted({s for t in trails for s in t.status_sources})
    skipped = []
    for source in wanted:
        try:
            f.get("pages", source, PAGES[source].url)
        except Disallowed:
            skipped.append(source)
    return skipped


def collect(
    f: Fetcher, trails: list[Trail], stations: StationsFile, grid: GridFile, now: dt.datetime
) -> list[str]:
    collect_snotel(f, stations, f.day)
    collect_nws(f, grid, now)
    f.get(
        "reports", "recent", REPORTS_URL, headers={"Accept": "application/json"}, check_robots=False
    )
    return collect_pages(f, trails)


# --- One-off: resolve each trail's NWS gridpoint and nearest METAR station ----------------


def resolve_grid(f: Fetcher, trails: list[Trail], max_km: float = 40.0) -> GridFile:
    """Look up /points for each trailhead and the nearest ASOS/AWOS (K***) station.

    Run rarely (`dryline resolve`); the result is committed as nws_grid.yaml so daily runs
    don't repeat these lookups.
    """
    points: dict[str, tuple[str, str]] = {}
    metar: dict[str, ObsStation] = {}  # every K*** station from every gridpoint's list
    seen_lists: set[str] = set()
    for t in trails:
        p = t.high_point or t.trailhead
        url = f"{NWS_API}/points/{p.lat:.4f},{p.lon:.4f}"
        raw = f.get("nws-resolve", f"points-{t.id}", url, headers=GEOJSON, check_robots=False)
        if not raw.ok:
            continue
        props = raw.json_body()["properties"]
        points[t.id] = (url, props["forecast"])
        stations_url = props["observationStations"]
        if stations_url in seen_lists:
            continue
        seen_lists.add(stations_url)
        name = f"stations-{props['gridId']}-{props['gridX']}-{props['gridY']}"
        sraw = f.get("nws-resolve", name, stations_url, headers=GEOJSON, check_robots=False)
        for feat in sraw.json_body().get("features", []) if sraw.ok else []:
            sid = feat["properties"]["stationIdentifier"]
            if len(sid) == 4 and sid.startswith("K") and sid.isalpha():
                lon, lat = feat["geometry"]["coordinates"][:2]
                metar[sid] = ObsStation(id=sid, name=feat["properties"]["name"], lat=lat, lon=lon)
    entries: dict[str, GridEntry] = {}
    for t in trails:
        if t.id not in points:
            continue
        ranked = sorted(
            (km_between(t.trailhead, LatLon(lat=s.lat, lon=s.lon)), s.id) for s in metar.values()
        )
        best = metar[ranked[0][1]] if ranked and ranked[0][0] <= max_km else None
        entries[t.id] = GridEntry(
            points_url=points[t.id][0], forecast_url=points[t.id][1], obs_station=best
        )
    return GridFile(trails=entries)


def dump_grid(grid: GridFile) -> str:
    header = (
        "# NWS gridpoint forecast URL and nearest METAR station per trail.\n"
        "# Generated by `dryline resolve` from api.weather.gov /points and /stations.\n"
    )
    data = grid.model_dump(mode="json")
    return header + yaml.safe_dump(data, sort_keys=True, allow_unicode=True)
