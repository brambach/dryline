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

## M4: Rules and claims

`rules.evaluate` is deterministic. Precedence is closed > snow > muddy > dry > unknown, and "dry" needs
positive snow-free and low-rain evidence. The type wall:

- `Claim` requires an `HttpUrl` source, a timezone-aware `fetched_at`, and a non-empty quote.
- `TrailLine` refuses a non-unknown status without claims, and an unknown status without `Missing`
  entries, each of which carries the URL that was tried.
- `build_site` raises `TypeError` for anything that isn't a `TrailLine`.
- Each page is run through `check_every_line_linked` at build time. It raises `UncitedLine` if a rendered
  line lacks an `a[data-source][href^=http]`.

```
$ uv run pytest -v tests/test_rules.py tests/test_site.py tests/test_end_to_end.py
test_rules.py::test_dry_needs_snow_free_and_low_rain PASSED
test_rules.py::test_snow_at_similar_elevation_below_high_point PASSED
test_rules.py::test_snow_only_above_trail_is_not_snow PASSED
test_rules.py::test_snow_depth_noise_below_threshold_is_not_snow PASSED
test_rules.py::test_muddy_after_rain PASSED
test_rules.py::test_closed_beats_everything PASSED
test_rules.py::test_unrelated_closure_ignored PASSED
test_rules.py::test_closure_keyword_in_summary PASSED
test_rules.py::test_unknown_when_no_snow_station PASSED
test_rules.py::test_stale_snotel_counts_as_missing PASSED
test_rules.py::test_far_station_ignored PASSED
test_rules.py::test_station_outside_elevation_band_ignored PASSED
test_rules.py::test_patchy_precip_counts_as_missing PASSED
test_rules.py::test_old_nws_window_counts_as_missing PASSED
test_rules.py::test_fresh_conditions_page_muddy PASSED
test_rules.py::test_stale_conditions_page_is_missing_not_used PASSED
test_rules.py::test_snow_free_conditions_entry_is_not_dry_without_rain_data PASSED
test_rules.py::test_source_gap_is_reported PASSED
test_rules.py::test_line_without_claims_cannot_say_dry PASSED
test_rules.py::test_unknown_must_say_what_is_missing PASSED
test_rules.py::test_claim_requires_citation[bad0] PASSED
test_rules.py::test_claim_requires_citation[bad1] PASSED
test_rules.py::test_claim_requires_citation[bad2] PASSED
test_rules.py::test_claim_requires_citation[bad3] PASSED
test_rules.py::test_claim_requires_citation[bad4] PASSED
test_rules.py::test_gap_for_unrelated_source_not_shown PASSED
test_rules.py::test_snow_free_witness_prefers_near_station_above_high_point PASSED
test_site.py::test_builds_all_pages PASSED
test_site.py::test_every_rendered_line_has_a_source_link PASSED
test_site.py::test_uncited_line_is_rejected PASSED
test_site.py::test_feed_parses PASSED
test_end_to_end.py::test_one_line_per_trail PASSED
test_end_to_end.py::test_every_page_every_line_linked PASSED
test_end_to_end.py::test_missing_source_shows_up PASSED
test_end_to_end.py::test_renderer_rejects_non_lines PASSED
$ uv run pytest -q
73 passed, 1 warning in 0.95s
```

## M5: Site and RSS

```
$ uv run dryline build --date 2026-10-16
2026-10-16: 18 dry, 2 unknown
wrote 27 files to site            # index, today.json, feed.xml, archive/, 20 trail pages, fonts

$ uv run python scripts/screenshots.py
docs/screenshots/today-mobile.png  horizontal-overflow=False
docs/screenshots/archive-mobile.png  horizontal-overflow=False
docs/screenshots/trail-mobile.png  horizontal-overflow=False
docs/screenshots/today-desktop.png  horizontal-overflow=False
docs/screenshots/archive-desktop.png  horizontal-overflow=False
docs/screenshots/trail-desktop.png  horizontal-overflow=False

$ uv run python -c "import feedparser; ..."
bozo: False | title: dryline: Tahoe trail conditions | entries: 1
entry 0: Fri Oct 16: 18 dry, 2 unknown | https://brambach.github.io/dryline/archive/2026-10-16/
```

`tests/test_site.py::test_feed_parses` asserts the same thing offline. Mobile is 390×844 at 2×, desktop
1280×900. Screenshots are taken with reduced motion, so the one "Today" arrival animation doesn't blur them.
The fonts (Fraunces, Hanken Grotesk, IBM Plex Mono, all SIL OFL) are self-hosted.

## M6: Eval harness

`labels/trail-days.csv` holds the real labels and is empty, waiting for your 50 trail-days.
`labels/SYNTHETIC-sample.csv` has 5 made-up rows, each with a note saying "SYNTHETIC", and
`dryline eval` prints a warning banner when it sees them.

```
$ uv run dryline eval --labels labels/SYNTHETIC-sample.csv
NOTE: these labels are SYNTHETIC. The numbers below test the harness only.

labels: 5   scored: 5   no prediction: 0

truth     correct  total  accuracy
dry             2      3       67%
muddy           0      1        0%
snow            0      1        0%

unknown rate: 40%
accuracy when not unknown: 2/3 = 67%

truth \ predicted       dry    muddy     snow   closed  unknown
dry                       2        0        0        0        1
muddy                     1        0        0        0        0
snow                      0        0        0        0        1

$ uv run dryline eval
labels/trail-days.csv: no labels yet. Run `dryline label` to add some.
```

Labeling page smoke test: `uv run dryline label --labels <tmp>.csv --port 8799`.

- `GET /` rendered 20 trail rows for 2026-10-16.
- `POST /label {"date":"2026-10-16","trail":"castle-peak","truth":"dry"}` returned `{"ok": true}` and
  wrote the row.

dryline's own call is hidden behind a "dryline said" disclosure, so it doesn't anchor the labeler.
`tests/test_eval.py` covers scoring, upserts, and the page.

## Review fixes (after M6)

An independent review found these problems. Each one now has a regression test.

- **Snow:** snow reported only above the high point produced "dry" with no bare-ground witness.
  "Dry" now needs a bare station within 1,000 ft of the high point.
- **SNOTEL precipitation windows:** they could end up to 48 h before the run while the claim said
  "last 48 h". Windows must now end within 30 h, and the claim names its dates.
- **NWS observations:**
  - The window ended at the last report of any kind; it now ends at the last report that counted.
  - A later SPECI could replace the hour's routine METAR; now only routine reports count.
  - A missing P-group counted as zero rain at AWOS stations; it now does so only at verified ASOS
    stations (KTVL).
- **Conditions text:** "No closures" read as closed and "No mud" as muddy. Negation is now handled.
- **Rebuild date:** `build --date` used the wall clock for freshness and dated lines by `now`. Lines now
  take the given day, and freshness uses that day's fetch time.
- **TRTA:** a missing segment produced no Missing entry, and a "free of snow" entry alone could stand in
  for SNOTEL. Both are fixed.
- **NV State Parks:** a missing alert list was silent, and a relative link crashed the build. Both are
  fixed, and any malformed response now becomes a gap instead of a crash.
- **RSS:** the description wasn't escaped; it's now CDATA and includes fetch times.
- **Smaller fixes:**
  - Closures with a future start date are ignored.
  - Failed fetches are retried the same day.
  - The "Overnight" forecast period no longer shows up in a 5:40am run.
  - The index no longer labels an old day "Today".
  - The labeling server accepts JSON only.
  - A `--now` without an offset is read as Pacific time.

```
$ uv run pytest -q
90 passed, 1 warning in 1.11s
$ uv run dryline build --date 2026-10-16
2026-10-16: 18 dry, 2 unknown
```

## Second live run: Oct 17 morning

At 14:10 UTC there was no workflow commit on `claude/dryline-mvp`, and the GitHub API reports **0 workflow
runs**. The 13:40 UTC cron hasn't fired yet: new schedules can take a while to activate, or Actions may
be disabled for the repo. I ran the morning collection locally instead:

```
$ uv run dryline collect        # 2026-10-17 14:11 UTC = 7:11am PDT
... 29 requests, all 200 (SNOTEL x1, NWS forecasts x19, NWS observations x3, official pages x5, robots.txt per host)
$ uv run dryline build
2026-10-17: 18 dry, 2 unknown
wrote 29 files to site
$ feedparser site/feed.xml
bozo: False | entries: 2 | Sat Oct 17: 18 dry, 2 unknown / Fri Oct 16: 18 dry, 2 unknown
$ uv run pytest -q
90 passed, 1 warning in 1.02s
```

SNOTEL now has Oct 16 values. The NWS "Today" period is selected (for example "Sunny, high 58°F" at Eagle
Lake), and KTVL's precipitation window ends at 5:53am. The archive now holds Oct 16 and Oct 17, and the
screenshots were re-taken from this build.

## Design pass: design-taste

The site was rebuilt to github.com/brambach/design-taste (`APPLY.md`, `built/dervo.md`, starter tokens).
`docs/DESIGN.md` records how each rule was applied and the two deliberate deviations.

- **Type:** Instrument Serif, Instrument Sans and JetBrains Mono, all self-hosted under OFL. This replaces
  Fraunces, Hanken Grotesk and IBM Plex Mono.
- **Ground:** warm paper, with the warm-charcoal dark theme.
- **Status:** drawn glyphs plus a word, and lines grouped by status so the word is said once.
- **Rows:** no rule lines; hovering one dims the others.
- **Accent:** rust appears only on "closed".
- **Motion:** the "Today" arrival animation is gone (nothing animates on load).
- **Scene:** one halftone ridgeline behind the title. Ridge, wash and none options are rendered side by
  side in `docs/screenshots/options/`.

```
$ uv run python scripts/screenshots.py      # 1052x854 @2x and 390x844 @2x
docs/screenshots/{today,archive,trail}-{mobile,desktop}.png  horizontal-overflow=False (6/6)
docs/screenshots/options/scene-{ridge,wash,none}-{mobile,desktop}.png
$ uv run pytest -q
90 passed
```

## The daily workflow ran

GitHub Actions fired the 13:40 UTC cron at **16:39 UTC** (scheduled runs often start late) and committed
`9c1b619 data: 2026-10-17` as dryline-bot. It found today's raw files already committed, so it made **no
new requests**, which is the per-day cache working as designed, and only rebuilt.

That rebuild exposed drift: it judged freshness against the wall clock, so KTVL's window shrank from 47 h
to 45 h. `dryline build` now judges freshness as of the snapshot's latest `fetched_at` unless you pass
`--now`, so rebuilding the same raw data gives byte-identical `data/lines/*.json`. Only the "Built"
stamp in the site changes.

## Shared design tokens

The roughly 36 hand-copied variables in `style.css` are gone. dryline now loads the shared
`@brambach/design-tokens` v0.1.0, vendored at design-taste commit `e8404234a6e8` (not yet merged or
tagged), from `src/dryline/templates/design-tokens/`. This run couldn't read the private repo, so the
copy came from an exact tarball of that commit. `VERSION` and `SHA256SUMS` were written in the format
`sync.sh` uses, so `--check` works, and future bumps can use `sync.sh --ref <tag>`. Every replaced value
matched the shared tokens exactly. The one exception was dark `--lift`, which nothing in dryline uses.
`style.css` keeps only `--scene` and the status colors, with `--dry` and `--closed` pointing at the
shared `--done` and `--accent`.

```
$ sh src/dryline/templates/design-tokens/sync.sh --check
design-tokens: src/dryline/templates/design-tokens matches e8404234a6e8570c4c79002aca256b1483e3e95e (e8404234a6e8)
$ uv run pytest -q && uv run ruff check
94 passed, 1 warning in 0.82s
All checks passed!
$ uv run dryline build
2026-10-18: no raw data; rendering existing lines only
wrote 34 files to /workspace/site
$ uv run python scripts/screenshots.py
docs/screenshots/{today,archive,trail}-{mobile,desktop}.png  horizontal-overflow=False (6/6)
```

Before and after screenshots (light, plus dark for the today and trail pages) are pixel-identical,
except for one digit of the "Built" time in the footer. Rebuilding on Oct 18 before that day's data
is collected shows "Saturday" and the stale notice instead of "Today", both before and after this change.

## M7: Trail forecast (Oct 30, 2026)

The brief: turn the digest into a surf forecast for trails. Dry-by forecast, the ridge, rider reports,
a morning email, a published hit rate.

```
$ uv run pytest -q
118 passed
$ for d in 16..23: uv run dryline build --date 2026-10-$d
2026-10-22: forecast for 20 trails, 19 with a dry-by day
2026-10-23: forecast for 20 trails, 20 with a dry-by day
```

Backtest on the archive: the Oct 19 forecast called muddy from Wednesday Oct 22 on the trails that got
the storm, and Oct 22 was muddy. See How it works on the site for the scored table. The sandbox that built
this can't reach NWS or SNOTEL, so the forecast was only run on the archived snapshots; the daily
workflow runs it live.
