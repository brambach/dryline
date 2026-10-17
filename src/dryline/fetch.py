"""Polite fetching: one request per URL per day, robots.txt honored, raw envelope saved to disk."""

from __future__ import annotations

import datetime as dt
import gzip
import hashlib
import json
import urllib.robotparser
from pathlib import Path
from urllib.parse import urlencode, urlsplit

import httpx
from pydantic import AwareDatetime, BaseModel

USER_AGENT = "dryline (github.com/brambach/dryline)"
TIMEOUT = httpx.Timeout(30.0)


class RawResponse(BaseModel):
    """A raw response exactly as fetched, plus when and from where."""

    source: str
    url: str
    fetched_at: AwareDatetime
    status_code: int
    content_type: str
    body: str

    @property
    def ok(self) -> bool:
        return 200 <= self.status_code < 300

    def json_body(self):
        return json.loads(self.body)


class Disallowed(Exception):
    """robots.txt disallows this URL for our user agent."""


def full_url(url: str, params: dict[str, str] | None = None) -> str:
    if not params:
        return url
    return f"{url}{'&' if '?' in url else '?'}{urlencode(params)}"


def day_dir(root: Path, day: dt.date) -> Path:
    return root / day.isoformat()


def raw_path(root: Path, day: dt.date, source: str, name: str) -> Path:
    return day_dir(root, day) / source / f"{name}.json.gz"


def load_raw(path: Path) -> RawResponse:
    return RawResponse.model_validate_json(gzip.decompress(path.read_bytes()))


def save_raw(path: Path, raw: RawResponse) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # mtime=0 keeps the bytes stable, so re-saving the same response makes no git diff
    path.write_bytes(gzip.compress(raw.model_dump_json(indent=1).encode(), mtime=0))


class Fetcher:
    def __init__(
        self,
        raw_root: Path,
        day: dt.date,
        client: httpx.Client | None = None,
        now=lambda: dt.datetime.now(dt.UTC),
    ):
        self.raw_root = raw_root
        self.day = day
        self.client = client or httpx.Client(
            headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT, follow_redirects=True
        )
        self.now = now
        self._robots: dict[str, urllib.robotparser.RobotFileParser] = {}
        self.log: list[str] = []

    def allowed(self, url: str) -> bool:
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        if origin not in self._robots:
            parser = urllib.robotparser.RobotFileParser()
            try:
                resp = self.client.get(f"{origin}/robots.txt")
            except httpx.HTTPError:
                resp = None
            if resp is None or resp.status_code >= 500:
                parser.disallow_all = True  # can't read robots.txt: stay away
            elif resp.status_code >= 400:
                parser.allow_all = True  # no robots.txt
            else:
                parser.parse(resp.text.splitlines())
            self._robots[origin] = parser
        return self._robots[origin].can_fetch(USER_AGENT, url)

    def get(
        self,
        source: str,
        name: str,
        url: str,
        params: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
        check_robots: bool = True,
    ) -> RawResponse:
        """Fetch once per day. A cached file for today is returned without touching the network."""
        path = raw_path(self.raw_root, self.day, source, name)
        if path.exists():
            self.log.append(f"cache {url}")
            return load_raw(path)
        target = full_url(url, params)
        if check_robots and not self.allowed(target):
            self.log.append(f"robots-disallowed {target}")
            raise Disallowed(target)
        fetched_at = self.now()
        try:
            resp = self.client.get(target, headers=headers or {})
            raw = RawResponse(
                source=source,
                url=str(resp.url),
                fetched_at=fetched_at,
                status_code=resp.status_code,
                content_type=resp.headers.get("content-type", ""),
                body=resp.text,
            )
        except httpx.HTTPError as exc:
            raw = RawResponse(
                source=source,
                url=target,
                fetched_at=fetched_at,
                status_code=0,
                content_type="",
                body=f"{type(exc).__name__}: {exc}",
            )
        save_raw(path, raw)
        self.log.append(f"{raw.status_code} {target}")
        return raw


def short_hash(text: str) -> str:
    return hashlib.sha1(text.encode()).hexdigest()[:10]
