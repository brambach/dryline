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
