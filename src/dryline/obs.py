"""Typed observations parsed from raw responses. Each one carries its own citation."""

from __future__ import annotations

import datetime as dt
import math
from typing import Literal

from pydantic import AwareDatetime, Field, HttpUrl

from dryline.models import Claim, LatLon, Missing, PageSource, Strict


class Cited(Strict):
    source_name: str
    source_url: HttpUrl
    fetched_at: AwareDatetime
    quote: str = Field(min_length=1)

    def claim(self, kind, statement: str, observed_at: dt.datetime | None = None) -> Claim:
        return Claim(
            kind=kind,
            statement=statement,
            source_name=self.source_name,
            source_url=self.source_url,
            fetched_at=self.fetched_at,
            quote=self.quote,
            observed_at=observed_at,
        )


class SnowObs(Cited):
    """SNOTEL snow depth for one station-day."""

    station_id: str
    station_name: str
    location: LatLon
    elevation_ft: int
    date: dt.date
    depth_in: float
    swe_in: float | None = None  # snow water equivalent (WTEQ), when the station reports it


class PrecipObs(Cited):
    """Liquid precipitation total over a window at one station."""

    network: Literal["NWS", "SNOTEL"]
    station_id: str
    station_name: str
    location: LatLon
    window_start: AwareDatetime
    window_end: AwareDatetime
    total_in: float
    periods_reported: int
    periods_expected: int
    dry_capable: bool = True  # can a missing report group be read as "no precipitation"?


class ClosureObs(Cited):
    """An official alert whose title names a closure."""

    page: PageSource
    title: str
    summary: str = ""
    link: HttpUrl
    published: dt.date | None = None


class ConditionsObs(Cited):
    """One entry on an official conditions page (for example, a TRT segment)."""

    segment: str
    text: str
    last_updated: dt.date
    hint: Literal["closed", "snow", "muddy", "snow_free"] | None = None


class ForecastObs(Cited):
    period: str
    short_forecast: str
    start: AwareDatetime


class ForecastPeriod(Cited):
    """One 12-hour NWS forecast period, with the amounts NWS spells out in words."""

    name: str
    start: AwareDatetime
    end: AwareDatetime
    is_daytime: bool
    temp_f: int
    pop: int = 0  # chance of precipitation, percent
    short_forecast: str
    rain_in: float | None = None  # "New rainfall amounts between a quarter and half of an inch"
    snow_in: float | None = None  # "New snow accumulation of 1 to 3 inches"
    snow_level_ft: int | None = None  # "Snow level 7500 feet"
    grid_elevation_ft: int  # elevation NWS forecast this gridpoint for


class Gap(Strict):
    """A source we tried and could not use today."""

    source: PageSource
    what: str
    tried_url: HttpUrl

    def missing(self) -> Missing:
        return Missing(what=self.what, tried_url=self.tried_url)


class Observations(Strict):
    snow: tuple[SnowObs, ...] = ()
    precip: tuple[PrecipObs, ...] = ()
    closures: tuple[ClosureObs, ...] = ()
    conditions: tuple[ConditionsObs, ...] = ()
    forecasts: dict[str, ForecastObs] = Field(default_factory=dict)
    outlooks: dict[str, tuple[ForecastPeriod, ...]] = Field(default_factory=dict)
    gaps: tuple[Gap, ...] = ()


def km_between(a: LatLon, b: LatLon) -> float:
    r = 6371.0
    p1, p2 = math.radians(a.lat), math.radians(b.lat)
    dp, dl = p2 - p1, math.radians(b.lon - a.lon)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))
