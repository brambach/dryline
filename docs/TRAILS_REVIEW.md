# Reviewing trails.yaml

All 20 trails are `confirmed: false`. When a trail looks right, set it to `confirmed: true`. The trail page
shows "Draft, not yet reviewed" until then.

## Choices made while drafting

- **Dropped from the candidate list:**
  - Tahoe Meadows to Ophir Creek: Ophir Creek drains to Washoe Valley, outside the basin.
  - Shirley Canyon: informal, partly on private land, with no official page.
  - Page Meadows was added in their place.
- **Min/max elevation and aspect** were sampled from USGS 3DEP elevations along the OpenStreetMap trail
  line. They're computed, not published, figures, and can be 5–30 ft off.
- **Summits** use NGS benchmark datasheets (NAVD88) where they exist: Tallac 9,739, Rose 10,785, Castle 9,109.
  USFS pages list some of these a few feet lower on an older datum.
- **USFS pages for Eagle Falls and Bayview** say about 7,100 ft. USGS elevation at the USFS coordinates gives
  about 6,574 and 6,836 ft, and the draft uses those.

## Weak or estimated entries (check these first)

| Trail | What to check |
|---|---|
| corral-trail | No official page or coordinates; both access points come from OSM. Manager is assumed to be LTBMU. |
| ellis-peak | Summit 8,730 ft from elevation data (often published as 8,740). Trailhead from OSM. Bikes allowed? Manager LTBMU or Tahoe NF? |
| mr-toads-wild-ride | High point 8,954 ft near Tucker Flat is computed. Shuttle route; only the climb from Big Meadow is TRT (segment KBStoBM). |
| donner-lake-rim-trail | The OSM line has a gap near Summit Lake, so the max of 7,689 ft may be too low. No machine-readable closure source (land trust). |
| trt-brockway-to-martis-peak | Martis Peak 8,736 ft from elevation data (often published as 8,742). Trailhead from OSM. |
| mount-judah-loop | No Tahoe NF page. Trailhead from OSM. Crosses Sugar Bowl land. |
| page-meadows | Trailhead from OSM; the 6,532 ft min is the Ward Creek access. Manager assumed LTBMU. |
| castle-peak | Tahoe NF moved the trailhead north of I-80 (decision 12/2025). The coordinates may be the old one. |
| five-lakes, castle-peak, sawtooth-trail | Trailheads from OSM. |

## Closure keywords

Keywords are matched against official alert titles and summaries, but only from the trail's own
`status_sources`. They were tightened to trail names, because broad words matched unrelated alerts: "mount
rose" matched the highway, "corral" matched Camp Richardson Corral, and "big meadow" matched the campground.

Two active alerts need your call. Neither is matched today:

- **Tahoe NF "Alpine Meadows Stewardship Agreement Closure"** (May 2026 to Jan 2027). Its boundary is
  described only in legal terms. If it covers the Five Lakes trail, add `alpine meadows` to five-lakes'
  `closure_keywords`.
- **Tahoe NF "Big Chief Sale Closure"** closes system roads and trails in the Big Chief project area next
  to the Sawtooth Trail. If it covers Sawtooth, add `big chief`.

## No closure source dryline can read

- **rubicon-trail-dl-bliss:** California State Parks' Conditions of Use forbid automated access. The line
  says so and links the parks page.
- **donner-lake-rim-trail:** Truckee Donner Land Trust has no conditions page.

## Other context from research (not in the rules)

- D.L. Bliss has been closed to vehicles since Oct 1, so Rubicon is walk-in.
- Van Sickle is open to vehicles May 1 to Oct 31.
- Spooner, Marlette and the Flume had weekday construction closures in 2026, per TRTA citing NV State Parks.
- TAMBA reports forest operations on Toad's, Saxon Creek and Corral.
