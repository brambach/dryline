# dryline plan

One page each morning: "where can I go today?" for 20 Tahoe-basin and Truckee trails.
One line per trail: **dry**, **muddy**, **snow**, **closed**, or **unknown**, with the reason.
Every claim cites a source URL and a fetch time. No source means "unknown" plus what's missing.

## Milestones

| | Milestone | Check |
|---|---|---|
| M0 | Scaffold: uv package, CLI stub, `CLAUDE.md`, SessionStart hook | `uv run pytest && uv run ruff check` |
| M1 | `trails.yaml` (20 trails, `confirmed: false`) and a pydantic schema | Test fails if a trail lacks a source URL or sits outside the Tahoe bbox |
| M2 | NWS and SNOTEL collectors, raw snapshots in `data/raw/YYYY-MM-DD/` | Fixture tests with sockets disabled (pytest-socket); one live run logged |
| M3 | Official condition and closure pages (robots.txt and terms checked) | Fixture tests, including a changed layout that yields "unknown" |
| M4 | Deterministic rules producing `Claim` objects; renderer accepts only claims | Tests per rule, for unknown cases, and that every rendered line has a link |
| M5 | Static site: today, per-trail pages, archive, RSS, JSON | Build; Playwright screenshots (mobile, desktop); feed parses with feedparser |
| M6 | Eval: `labels/trail-days.csv`, `dryline eval`, local labeling page | `uv run dryline eval` on a 5-row sample clearly marked synthetic |

Each milestone ends with evidence in `PROGRESS.md` (command and output tail), plus a commit and push.

## Layout

```
trails.yaml                 20 trails, each with sources and confirmed: false
stations.yaml               SNOTEL stations (from AWDB metadata) and NWS obs stations
src/dryline/
  cli.py                    dryline collect | build | eval | label
  models.py                 Trail, Station, Claim, Missing, TrailLine (the type wall)
  fetch.py                  polite fetcher: UA, robots.txt check, one request per URL per day, raw envelope
  collectors/nws.py         gridpoint forecast and station observations
  collectors/snotel.py      AWDB REST: SNWD and WTEQ daily for all stations in one request
  collectors/pages.py       TRTA conditions page and USFS alert listings
  parse/                    raw envelope -> typed observations (each keeps url, fetched_at, quote)
  rules.py                  observations -> TrailLine (claims or missing); no LLM, no guessing
  site.py                   jinja2 -> site/ (index, trails/<id>/, archive/, feed.xml, today.json)
  evaluate.py               labels CSV vs. archived TrailLines: per-class accuracy, unknown rate
  label.py                  tiny local http.server labeling page that writes labels/trail-days.csv
  templates/
data/raw/YYYY-MM-DD/        raw responses, each wrapped as {url, fetched_at, status, body}
data/lines/YYYY-MM-DD.json  the day's TrailLines (the archive source of truth)
site/                       built static output (committed by the daily workflow)
tests/fixtures/             recorded responses; tests never touch the network
```

## Rules (first cut, thresholds in one config module)

Precedence: closed > snow > muddy > dry > unknown.

- **closed**: an official alert or conditions entry that matches the trail's `closure_keywords` and says closed or closure. Quoted text and URL.
- **snow**: a fresh SNOTEL station within 40 km and within ±1,000 ft of the trail's elevation band reports snow depth ≥ 2 in (sensors read 0–1 in of noise on bare ground). Claim: "Snow likely above ~X ft: <station> (<elev> ft) reported <n> in." Snow applies if the trail's max elevation ≥ X.
- **muddy**: 48 h precipitation ≥ 0.25 in at the nearest SNOTEL gauge (daily PRCP) or nearest METAR station (hourly P-groups), or a fresh official conditions entry that says muddy.
- **dry**: positive evidence only. Similar-elevation SNOTEL shows 0 in depth, *and* 48 h precipitation is below threshold with enough non-null hours. Otherwise unknown.
- **unknown**: lists what is missing (for example "no SNOTEL station within ±1,000 ft reported in the last 2 days"), each with the URL that was tried.
- Freshness windows: SNOTEL 2 days, NWS observations 6 h before the run, conditions pages 14 days since "last updated". Anything stale counts as missing.

## Type wall

`Claim(statement, source_url: HttpUrl, fetched_at: aware datetime, quote: non-empty str)`.
`TrailLine(status, claims, missing)`. Validators: non-unknown needs ≥1 claim; unknown needs ≥1 `Missing` (which also carries the URL tried).
Templates get only `TrailLine` objects, and every visible sentence comes from `Claim.statement` or `Missing.what`. A build-time check fails if any rendered line lacks an `<a href>`.

## Risks

- **NWS precipitation is often null** at ASOS stations, and `precipitationLastHour` gaps are common. Mitigation: read raw METAR P-groups instead, and require ≥ 60% of 48 hourly reports, otherwise precipitation is missing, and the trail goes unknown instead of dry.
- **Snow line from a few stations is coarse.** Aspect and shading matter in October. The wording stays "likely". The claim states the station and its elevation so readers can judge.
- **Page layouts change.** Parsers look for explicit anchors such as "last updated" and segment headings, and return nothing (so the trail is unknown) when the anchors are missing. A fixture test covers this.
- **USFS site migration.** fs.usda.gov moved to `/r05/...` URLs. URLs live in `trails.yaml` and `sources.yaml` for easy fixing.
- **Politeness.** Each distinct URL is fetched at most once per day (the cache is keyed by date). The NWS points→gridpoint lookup is resolved once and stored, so daily runs only hit forecast and observation URLs.
- **Workflow push.** Pushing `.github/workflows/` may be rejected by token scope. Fallback is `docs/daily.yml`.

## Open questions (defaults chosen, change any)

1. Thresholds: 0.25 in / 48 h for muddy, 2 in depth for snow, ±1,000 ft station band, 40 km radius. Reasonable starting points; tune with eval.
2. Hosting: GitHub Pages from `site/` on the default branch (static, free).
3. Should "snow" mean any snow on the route (the default) or snow at the trailhead?
