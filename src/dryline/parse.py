"""Raw responses -> typed observations. Unexpected shapes become a Gap, never a guess."""

from __future__ import annotations

import datetime as dt
import re
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

from selectolax.lexbor import LexborHTMLParser as HTMLParser

from dryline.config import PAGES, ObsStation, SnotelStation
from dryline.fetch import RawResponse
from dryline.models import LatLon, PageSource
from dryline.obs import (
    ClosureObs,
    ConditionsObs,
    ForecastObs,
    Gap,
    PrecipObs,
    SnowObs,
)

PST = dt.timezone(dt.timedelta(hours=-8))  # SNOTEL dataTimeZone is fixed -8
LOCAL = ZoneInfo("America/Los_Angeles")
QUOTE_MAX = 280


def _clip(text: str, n: int = QUOTE_MAX) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


class ParseError(ValueError):
    pass


# --- SNOTEL (AWDB REST) ---------------------------------------------------------------


def parse_snotel(
    raw: RawResponse, stations: dict[str, SnotelStation]
) -> tuple[list[SnowObs], list[PrecipObs]]:
    if not raw.ok:
        raise ParseError(f"SNOTEL HTTP {raw.status_code}")
    body = raw.json_body()
    if not isinstance(body, list):
        raise ParseError("SNOTEL response is not a list")
    cite = dict(source_name="NRCS SNOTEL", source_url=raw.url, fetched_at=raw.fetched_at)
    fetched_day = raw.fetched_at.astimezone(PST).date()
    snow: list[SnowObs] = []
    precip: list[PrecipObs] = []
    for item in body:
        st = stations.get(item.get("stationTriplet", ""))
        if st is None:
            continue
        series: dict[str, dict[dt.date, float]] = {}
        for d in item.get("data") or []:
            element = d.get("stationElement") or {}
            code = element.get("elementCode")
            if not code or d.get("error") or element.get("ordinal", 1) != 1:
                continue
            values = {}
            for v in d.get("values") or []:
                if v.get("value") is None or not v.get("date"):
                    continue
                day = dt.date.fromisoformat(v["date"][:10])
                if day <= fetched_day:  # never trust a value dated after the fetch
                    values[day] = float(v["value"])
            series[code] = values
        for day, depth in sorted(series.get("SNWD", {}).items()):
            swe = series.get("WTEQ", {}).get(day)
            quote = f"{st.triplet} {day} SNWD={depth:g} in" + (
                f", WTEQ={swe:g} in" if swe is not None else ""
            )
            snow.append(
                SnowObs(
                    **cite,
                    quote=quote,
                    station_id=st.triplet,
                    station_name=st.name,
                    location=st.location,
                    elevation_ft=st.elevation_ft,
                    date=day,
                    depth_in=depth,
                )
            )
        prcp = series.get("PRCP", {})
        if prcp:
            last = max(prcp)
            window = [last - dt.timedelta(days=1), last]
            got = [d for d in window if d in prcp]
            quote = f"{st.triplet} PRCP " + ", ".join(f"{d}={prcp[d]:g} in" for d in got)
            precip.append(
                PrecipObs(
                    **cite,
                    quote=quote,
                    network="SNOTEL",
                    station_id=st.triplet,
                    station_name=st.name,
                    location=st.location,
                    window_start=dt.datetime.combine(window[0], dt.time(), PST),
                    window_end=dt.datetime.combine(last + dt.timedelta(days=1), dt.time(), PST),
                    total_in=sum(max(0.0, prcp[d]) for d in got),
                    periods_reported=len(got),
                    periods_expected=2,
                )
            )
    return snow, precip


# --- NWS --------------------------------------------------------------------------------

_P_GROUP = re.compile(r"\sP(\d{4})(?=\s|$)")


def parse_nws_observations(
    raw: RawResponse, station: ObsStation, now: dt.datetime, hours: int = 48, asos: bool = False
) -> PrecipObs:
    """Sum the hourly METAR precipitation groups (Prrrr) over the last `hours`.

    The API's precipitationLastHour is null both for "none" and "not reported", so we read the
    raw METAR instead. Only the routine report in each hour counts (minute 45-59, earliest one):
    a SPECI later in the hour carries precipitation since the routine report, not the hour's.
    For ASOS stations (`asos=True`), an AO2 report with no PNO remark and no Prrrr group means
    no measurable precipitation that hour. Elsewhere we can only add up groups that are present,
    so the result can show rain but not its absence (dry_capable=False).
    """
    if not raw.ok:
        raise ParseError(f"NWS observations HTTP {raw.status_code}")
    features = raw.json_body().get("features")
    if not isinstance(features, list):
        raise ParseError("NWS observations: no features list")
    start = now - dt.timedelta(hours=hours)
    routine: dict[dt.datetime, tuple[dt.datetime, str]] = {}
    for f in features:
        p = f.get("properties") or {}
        msg = (p.get("rawMessage") or "").strip()
        if not msg or not p.get("timestamp"):
            continue
        t = dt.datetime.fromisoformat(p["timestamp"])
        if not start < t <= now or t.minute < 45:
            continue
        hour = t.replace(minute=0, second=0, microsecond=0)
        if hour not in routine or t < routine[hour][0]:
            routine[hour] = (t, msg)
    total = 0.0
    counted: list[dt.datetime] = []
    groups: list[str] = []
    for _, (t, msg) in sorted(routine.items()):
        rmk = msg.split(" RMK ", 1)[1] if " RMK " in msg else ""
        if "AO2" not in rmk or re.search(r"\bPNO\b", rmk):
            continue  # no precipitation sensor reading this hour
        counted.append(t)
        if m := _P_GROUP.search(" " + rmk):
            total += int(m.group(1)) / 100
            groups.append(f"P{m.group(1)}@{t:%d%H%M}Z")
    if not counted:
        raise ParseError(f"NWS {station.id}: no routine AO2 METARs in the last {hours} h")
    quote = (
        f"{station.id}: {len(counted)} routine METARs with AO2 from {counted[0]:%d%H%M}Z to "
        f"{counted[-1]:%d%H%M}Z; precipitation groups: {', '.join(groups) or 'none'}"
    )
    return PrecipObs(
        source_name="NWS observations",
        source_url=raw.url,
        fetched_at=raw.fetched_at,
        quote=_clip(quote),
        network="NWS",
        station_id=station.id,
        station_name=station.name,
        location=LatLon(lat=station.lat, lon=station.lon),
        window_start=counted[0] - dt.timedelta(hours=1),  # Prrrr covers the hour before
        window_end=counted[-1],
        total_in=round(total, 2),
        periods_reported=len(counted),
        periods_expected=hours,
        dry_capable=asos,
    )


def parse_nws_forecast(raw: RawResponse, now: dt.datetime, max_age_h: int = 18) -> ForecastObs:
    if not raw.ok:
        raise ParseError(f"NWS forecast HTTP {raw.status_code}")
    props = raw.json_body().get("properties") or {}
    periods = props.get("periods") or []
    updated = props.get("updateTime") or props.get("generatedAt")
    if not periods or not updated:
        raise ParseError("NWS forecast: no periods")
    if now - dt.datetime.fromisoformat(updated) > dt.timedelta(hours=max_age_h):
        raise ParseError(f"NWS forecast is stale (updated {updated})")
    soon = now + dt.timedelta(hours=2)  # skip "Overnight" ending at 6am for a 5:40am run
    end_ok = [
        p for p in periods if dt.datetime.fromisoformat(p["endTime"]) > soon and p.get("name")
    ]
    if not end_ok:
        raise ParseError("NWS forecast: no current period")
    p = end_ok[0]
    temp = f", {'high' if p.get('isDaytime') else 'low'} {p['temperature']}°{p['temperatureUnit']}"
    return ForecastObs(
        source_name="NWS forecast",
        source_url=raw.url,
        fetched_at=raw.fetched_at,
        quote=_clip(f"{p['name']}: {p.get('shortForecast', '')}{temp}"),
        period=p["name"],
        short_forecast=f"{p.get('shortForecast', '')}{temp}",
        start=dt.datetime.fromisoformat(p["startTime"]),
    )


# --- Official pages ----------------------------------------------------------------------

_CLOSURE = re.compile(r"\bclos(ed|ure|ures|ing)\b", re.I)
_SNOW_FREE = re.compile(r"(free|clear) of snow|snow[- ]free|no (remaining )?snow", re.I)
_MUD = re.compile(r"\bmud(dy)?\b", re.I)
_SNOW = re.compile(r"\bsnow", re.I)
_NEGATION = re.compile(
    r"\b(no|not|without|re-?opened|reopens?|lifted|ended)\b[\w\s,'-]{0,20}$", re.I
)
_UPDATED = re.compile(r"Last Updated:?\s*(\d{1,2})/(\d{1,2})/(\d{2,4})", re.I)


def _affirmed(pattern: re.Pattern, text: str) -> bool:
    """True if pattern occurs at least once without a negation in the few words before it."""
    return any(not _NEGATION.search(text[: m.start()]) for m in pattern.finditer(text))


def conditions_hint(text: str) -> str | None:
    """Classify an official conditions sentence. Deterministic and conservative."""
    if _affirmed(_CLOSURE, text):
        return "closed"
    if _affirmed(_MUD, text):
        return "muddy"
    stripped = _SNOW_FREE.sub("", text)
    if _affirmed(_SNOW, stripped):
        return "snow"
    if _SNOW_FREE.search(text):
        return "snow_free"
    return None


def _parse_us_date(text: str) -> dt.date | None:
    text = re.sub(r"\bSept\b", "Sep", text.strip())
    for fmt in ("%B %d, %Y", "%b %d, %Y"):
        try:
            return dt.datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    return None


def _gap(source: PageSource, what: str) -> Gap:
    return Gap(source=source, what=what, tried_url=PAGES[source].url)


def parse_trta(raw: RawResponse) -> tuple[list[ConditionsObs], list[Gap]]:
    """TRTA conditions page: one row per segment with 'Last Updated' and 'Trail Conditions'."""
    name = PAGES["trta"].name
    if not raw.ok:
        return [], [_gap("trta", f"{name} conditions page returned HTTP {raw.status_code}")]
    tree = HTMLParser(raw.body)
    out: list[ConditionsObs] = []
    unreadable: list[str] = []
    for row in tree.css("div.vc_row[id]"):
        seg = row.attributes.get("id") or ""
        heading = row.css_first("h2")
        if heading is None:
            continue
        m = _UPDATED.search(row.text(separator=" "))
        text = _section_text(row, "trail conditions")
        if m is None or text is None:
            unreadable.append(seg)
            continue
        month, day, year = (int(g) for g in m.groups())
        year = year + 2000 if year < 100 else year
        try:
            updated = dt.date(year, month, day)
        except ValueError:
            unreadable.append(seg)
            continue
        out.append(
            ConditionsObs(
                source_name=name,
                source_url=raw.url,
                fetched_at=raw.fetched_at,
                quote=_clip(text) or "(no trail conditions text)",
                segment=seg,
                text=_clip(text, 160) or "No trail conditions listed",
                last_updated=updated,
                hint=conditions_hint(text),
            )
        )
    gaps = []
    if not out:
        gaps.append(_gap("trta", f"{name} conditions page layout not recognized"))
    elif unreadable:
        gaps.append(
            _gap("trta", f"{name} entries without a readable date: {', '.join(unreadable)}")
        )
    return out, gaps


def _section_text(row, title: str) -> str | None:
    """Text of the <p> siblings after the h3 whose text matches title, up to the next h3."""
    for h3 in row.css("h3"):
        if h3.text(strip=True).lower().startswith(title):
            parts = []
            node = h3.next
            while node is not None and node.tag != "h3":
                if node.tag in ("p", "ul", "ol", "div"):
                    parts.append(node.text(separator=" ", strip=True))
                node = node.next
            return " ".join(p for p in parts if p)
    return None


def parse_usfs_alerts(raw: RawResponse, source: PageSource) -> tuple[list[ClosureObs], list[Gap]]:
    name = PAGES[source].name
    if not raw.ok:
        return [], [_gap(source, f"{name} page returned HTTP {raw.status_code}")]
    tree = HTMLParser(raw.body)
    container = tree.css_first("div.rows__container")
    if container is None:
        return [], [_gap(source, f"{name} page layout not recognized")]
    out = []
    for card in container.css("li.usa-card.wfs-alert-flag"):
        a = card.css_first("h3 a")
        if a is None or not a.attributes.get("href"):
            return [], [_gap(source, f"{name}: alert card without a link (layout changed?)")]
        title = a.text(strip=True)
        if not _CLOSURE.search(title):
            continue
        body = card.css_first(".usa-card__body")
        foot = card.css_first("footer")
        start = None
        if foot is not None and (
            m := re.search(r"Start Date:\s*([A-Z][a-z]+ \d{1,2}, \d{4})", foot.text())
        ):
            start = _parse_us_date(m.group(1))
        href = a.attributes["href"]
        out.append(
            ClosureObs(
                source_name=name,
                source_url=raw.url,
                fetched_at=raw.fetched_at,
                quote=_clip(title),
                page=source,
                title=_clip(title, 160),
                summary=_clip(body.text(separator=" ") if body else "", 600),
                link=urljoin(raw.url, href),
                published=start,
            )
        )
    return out, []


def parse_nvparks(raw: RawResponse) -> tuple[list[ClosureObs], list[Gap]]:
    source: PageSource = "nvparks-tahoe"
    name = PAGES[source].name
    if not raw.ok:
        return [], [_gap(source, f"{name} page returned HTTP {raw.status_code}")]
    tree = HTMLParser(raw.body)
    title = tree.css_first("title")
    if title is None or "lake tahoe" not in title.text().lower():
        return [], [_gap(source, f"{name} page layout not recognized")]
    if tree.css_first("ul#alert") is None:
        return [], [_gap(source, f"{name} alert banner not found (layout changed?)")]
    out = []
    for li in tree.css("ul#alert li"):
        h3 = li.css_first("h3")
        if h3 is None:
            continue
        heading = h3.text(strip=True)
        p = li.css_first("p")
        summary = p.text(strip=True) if p else ""
        if not _CLOSURE.search(f"{heading} {summary}"):
            continue
        more = li.css_first("a.read-more")
        out.append(
            ClosureObs(
                source_name=name,
                source_url=raw.url,
                fetched_at=raw.fetched_at,
                quote=_clip(f"{heading}: {summary}"),
                page=source,
                title=_clip(heading, 160),
                summary=_clip(summary, 600),
                link=urljoin(raw.url, (more.attributes.get("href") if more else None) or ""),
            )
        )
    return out, []
