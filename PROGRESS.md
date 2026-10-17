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
