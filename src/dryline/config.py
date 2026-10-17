"""Paths, source registry, and loaders for the committed YAML files."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml
from pydantic import HttpUrl

from dryline.models import LatLon, PageSource, Strict, Trail, TrailsFile


def project_root() -> Path:
    here = Path.cwd()
    for p in (here, *here.parents):
        if (p / "pyproject.toml").exists() and (p / "trails.yaml").exists():
            return p
    return here


@dataclass(frozen=True)
class Paths:
    root: Path

    @property
    def trails(self) -> Path:
        return self.root / "trails.yaml"

    @property
    def stations(self) -> Path:
        return self.root / "stations.yaml"

    @property
    def grid(self) -> Path:
        return self.root / "nws_grid.yaml"

    @property
    def raw(self) -> Path:
        return self.root / "data" / "raw"

    @property
    def lines(self) -> Path:
        return self.root / "data" / "lines"

    @property
    def site(self) -> Path:
        return self.root / "site"

    @property
    def labels(self) -> Path:
        return self.root / "labels" / "trail-days.csv"


@dataclass(frozen=True)
class PageSpec:
    name: str
    url: str


# Official pages, each checked against robots.txt and its terms (see SOURCES.md).
PAGES: dict[PageSource, PageSpec] = {
    "trta": PageSpec(
        "Tahoe Rim Trail Association", "https://tahoerimtrail.org/current-trail-conditions/"
    ),
    "usfs-ltbmu": PageSpec(
        "USFS Lake Tahoe Basin alerts", "https://www.fs.usda.gov/r05/laketahoebasin/alerts"
    ),
    "usfs-tnf": PageSpec("USFS Tahoe NF alerts", "https://www.fs.usda.gov/r05/tahoe/alerts"),
    "usfs-htnf": PageSpec(
        "USFS Humboldt-Toiyabe NF alerts", "https://www.fs.usda.gov/r04/humboldt-toiyabe/alerts"
    ),
    "nvparks-tahoe": PageSpec(
        "Nevada State Parks", "https://parks.nv.gov/parks/lake-tahoe-nevada-state-park"
    ),
}

# METAR stations verified as ASOS: routine hourly reports at :53 with SLP and 6-hour groups, so a
# missing Prrrr group means no measurable precipitation. KTRK and KCXP report every 20 minutes
# without SLP (AWOS); their reports can show rain but not its absence. Verify before adding.
ASOS_STATIONS = frozenset({"KTVL"})
AWDB_DATA_URL = "https://wcc.sc.egov.usda.gov/awdbRestApi/services/v1/data"
NWS_API = "https://api.weather.gov"


class SnotelStation(Strict):
    triplet: str
    name: str
    lat: float
    lon: float
    elevation_ft: int
    huc: str

    @property
    def location(self) -> LatLon:
        return LatLon(lat=self.lat, lon=self.lon)


class StationsFile(Strict):
    source_url: HttpUrl
    snotel: tuple[SnotelStation, ...]


class ObsStation(Strict):
    id: str
    name: str
    lat: float
    lon: float


class GridEntry(Strict):
    """NWS lookups for one trail, resolved once with `dryline resolve` and committed."""

    points_url: HttpUrl
    forecast_url: HttpUrl
    obs_station: ObsStation | None = None


class GridFile(Strict):
    trails: dict[str, GridEntry]


def load_trails(path: Path) -> list[Trail]:
    return list(TrailsFile.model_validate(yaml.safe_load(path.read_text())).trails)


def load_stations(path: Path) -> StationsFile:
    return StationsFile.model_validate(yaml.safe_load(path.read_text()))


def load_grid(path: Path) -> GridFile:
    if not path.exists():
        return GridFile(trails={})
    return GridFile.model_validate(yaml.safe_load(path.read_text()))
