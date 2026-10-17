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
