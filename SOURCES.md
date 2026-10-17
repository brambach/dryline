# Sources

Every source was checked against robots.txt and its terms on 2026-10-17. Each URL is fetched at most once
per day with the User-Agent `dryline (github.com/brambach/dryline)`. Raw responses are stored in
`data/raw/YYYY-MM-DD/`.

| Source | Used for | robots.txt | Terms | Decision |
|---|---|---|---|---|
| NRCS SNOTEL, AWDB REST API (`wcc.sc.egov.usda.gov/awdbRestApi`) | Snow depth, SWE, daily precipitation | None (404) | Federal public data | **Use**: one request per day for all 24 stations |
| NWS API (`api.weather.gov`) | Forecast, hourly METAR precipitation | `Disallow: /` for all agents | Public domain; asks API clients for an identifying User-Agent | **Use, flagged for review.** This is a documented machine API, and the disallow keeps crawlers out of search indexes. We send the requested User-Agent, cache by day, and resolve gridpoints once (`nws_grid.yaml`). |
| Tahoe Rim Trail Association conditions page | Segment conditions and "Last Updated" dates | `Allow: /` | No site terms found | **Use**: one fetch per day. Short quotes with a link back; no full-text republishing. |
| USFS alerts: Lake Tahoe Basin MU, Tahoe NF, Humboldt-Toiyabe NF (`www.fs.usda.gov/r05/...`, `/r04/...`) | Closure orders | Disallows only admin and search paths | Federal works | **Use** |
| Nevada State Parks, Lake Tahoe NSP page | Closure banners | None (404) | No anti-automation clause found | **Use**: banner alerts only |
| California State Parks (`parks.ca.gov`) | — | None | Conditions of Use forbid any "spider or other automatic device" | **Skip**. Rubicon Trail and other state-park trails link to the page for humans only. |
| Truckee Donner Land Trust | — | Pages allowed | — | **Skip**: no trail-conditions page exists |
| AllTrails, Strava | — | — | Terms forbid scraping | **Never** (non-goal) |

## Known quirks

- **NWS observation precipitation fields** (`precipitationLastHour` and similar) are null both for "none" and
  "not reported". dryline reads the raw METAR instead, using only the routine report each hour (minute
  45–59). For verified ASOS stations (KTVL), an AO2 report with no `PNO` remark and no `Prrrr` group
  counts as zero. KTRK and KCXP are AWOS (reports every 20 minutes, no SLP), so their P-groups count as
  rain evidence but never as "no rain".
- **SNOTEL daily values lag** about a day and omit missing days instead of returning nulls. Snow depth
  older than 2 days counts as missing. A daily precipitation window must end within 30 h, and the claim
  names its dates.
- **SNOTEL depth sensors** read 0–1 in of noise on bare ground, so "snow" needs at least 2 in.
- **The TRTA page** had "Updated August 17, 2026" at the top and segment dates in June and July as of
  October 17. Entries older than 14 days are treated as missing.

## Pattern references (studied, no code copied)

- simonw/ca-fires-history and "git scraping" (Simon Willison, 2020): the cron-commits-snapshots pattern.
  No license file, so only the pattern was used.
- weather-gov/api: User-Agent requirement and observation-precipitation quirks (discussions #622, #751, #872).
- nrcs-nwcc/iow_awdb_rest_api_demo: AWDB endpoint shapes. No license, so only the pattern was used.
- ulmo-dev/ulmo: BSD-3-Clause. Read for how it handles SNOTEL; nothing reused.
