# Progress

Evidence for each milestone: the command, then the tail of its output.

## M0: Scaffold

```
$ uv run pytest -q && uv run ruff check
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
2 passed, 1 warning in 0.01s
All checks passed!
```

The SessionStart hook in `.claude/settings.json` runs `uv sync` only when `CLAUDE_CODE_REMOTE=true`. It was checked by running its command with that variable set.

## M1: trails.yaml and schema

The 20 trails come from cited public sources (USFS, CA/NV State Parks, TRTA, NGS, USGS, OSM). All are
`confirmed: false`, and `docs/TRAILS_REVIEW.md` lists what to check. The `Trail` model rejects an
empty `sources` list and any point outside the Tahoe bounding box.

```
$ uv run pytest -q tests/test_trails.py
8 passed in 0.39s
```

`test_schema_rejects_missing_sources` and `test_schema_rejects_points_outside_tahoe` (Yosemite, Auburn,
Reno) confirm that a bad trail fails validation.

## M2: NWS and SNOTEL collectors

pytest-socket runs on every test through `addopts = "--disable-socket --allow-unix-socket"` in
`pyproject.toml`, and `tests/test_cli.py::test_network_is_blocked_in_tests` confirms that a socket
attempt fails. Fixtures are real recorded responses in `tests/fixtures/`.

```
$ uv run pytest -q tests/test_fetch.py tests/test_parse.py tests/test_cli.py
25 passed, 1 warning in 0.29s
```

**Live run, 2026-10-17 05:40–06:24 UTC** (2026-10-16 evening in Pacific time, so files land in
`data/raw/2026-10-16/`). `dryline resolve` ran once and wrote `nws_grid.yaml`: 19 distinct NWS gridpoints
and the nearest METAR stations KTVL, KTRK and KCXP. Then:

```
$ uv run dryline collect
cache https://wcc.sc.egov.usda.gov/awdbRestApi/services/v1/data          # fetched earlier that day
200 https://api.weather.gov/gridpoints/REV/27,101/forecast
  ... 19 gridpoint forecasts, all 200 ...
200 https://api.weather.gov/gridpoints/STO/94,66/forecast
200 https://api.weather.gov/stations/KCXP/observations?start=2026-10-15T05%3A23%3A52Z
200 https://api.weather.gov/stations/KTRK/observations?start=2026-10-15T05%3A23%3A52Z
200 https://api.weather.gov/stations/KTVL/observations?start=2026-10-15T05%3A23%3A52Z
200 https://parks.nv.gov/parks/lake-tahoe-nevada-state-park
200 https://tahoerimtrail.org/current-trail-conditions/
200 https://www.fs.usda.gov/r04/humboldt-toiyabe/alerts
200 https://www.fs.usda.gov/r05/laketahoebasin/alerts
200 https://www.fs.usda.gov/r05/tahoe/alerts
real 0m20.6s

$ uv run dryline build --date 2026-10-16
2026-10-16: 18 dry, 2 unknown
```

The SNOTEL request is a single call covering 24 stations (SNWD, WTEQ, PRCP). The latest daily value was
Oct 15, about 1 day of lag. NWS precipitation comes from the METAR P-groups, because the API's precipitation
fields are null for both "none" and "not reported". KTVL had 34 hourly METARs in 48 h with no P-groups.
The live SNOTEL response is kept as `tests/fixtures/snotel-prcp.json.gz`.

## M3: Official condition and closure pages

robots.txt and the terms were checked for every page (see `SOURCES.md`).

- **Used:** TRTA, USFS (LTBMU, Tahoe NF, Humboldt-Toiyabe), and the Lake Tahoe NV State Park page.
- **Skipped:**
  - CA State Parks: its Conditions of Use forbid automated access.
  - Truckee Donner Land Trust: it has no conditions page.

The parsers return a `Gap` (which renders as "unknown" or a caveat) when anchors are missing. They never
guess.

```
$ uv run pytest -v tests/test_parse.py   (page-related tests)
tests/test_parse.py::test_trta_segments_and_dates PASSED
tests/test_parse.py::test_trta_august_page_is_stale_on_october_17 PASSED
tests/test_parse.py::test_trta_changed_layout_yields_unknown_not_a_guess PASSED
tests/test_parse.py::test_trta_date_format_change_is_reported PASSED
tests/test_parse.py::test_usfs_closures_only PASSED
tests/test_parse.py::test_usfs_changed_layout_is_a_gap PASSED
tests/test_parse.py::test_http_error_is_a_gap PASSED
tests/test_parse.py::test_conditions_hint[This section is now completely free of snow!-snow_free] PASSED
tests/test_parse.py::test_conditions_hint[Trail is snow-free but muddy near the creek.-muddy] PASSED
tests/test_parse.py::test_conditions_hint[Patchy snow above 8,500 ft; otherwise clear of snow.-snow] PASSED
tests/test_parse.py::test_conditions_hint[Trail closed for construction.-closed] PASSED
tests/test_parse.py::test_conditions_hint[Expect mosquitos.-None] PASSED
tests/test_parse.py::test_nvparks_banner_without_closure PASSED
tests/test_parse.py::test_nvparks_closure_banner_and_changed_layout PASSED
22 passed in 0.24s
```

Live parse of the 2026-10-16 snapshot:

- **TRTA:** 9 segments, last updated Jun 24 to Jul 7. All are older than 14 days, so they're missing.
- **USFS:** closure alerts LTBMU 1, Tahoe NF 13, Humboldt-Toiyabe 17. None matches a trail's keywords.
- **NV State Parks:** banner only, no closures.
