# Design

dryline follows [github.com/brambach/design-taste](https://github.com/brambach/design-taste)
(`APPLY.md`, `built/dervo.md`, `tokens/tokens.css`). Its surface is product UI, read daily: calm, with taste
in a few places only. This file records how the rules were applied and where dryline deviates on purpose.

## Tokens

The shared tokens (`@brambach/design-tokens`, from `tokens/` in design-taste) are vendored, not copied
by hand, in `src/dryline/templates/design-tokens/`. `VERSION` records the pin (commit
`e8404234a6e8`, v0.1.0, untagged as of this writing). Pages load `tokens.css`, then `auto-dark.css`,
then `style.css`. The build copies the CSS to `site/design-tokens/`, and `theme-color` is read from
`tokens.json`. Don't edit the vendored files: `sync.sh --check` (CI and `tests/test_site.py`) fails if
they drift. Override in `style.css` instead. To bump, run `sh src/dryline/templates/design-tokens/sync.sh
--ref <tag>` on a machine that can read design-taste, then commit the folder.

`style.css` only defines dryline's own tokens: `--scene` and the five status colors. `--dry` is the
shared `--done` (sage) and `--closed` is the shared `--accent` (rust). `--muddy`, `--snow` and
`--unknown` have their own light and dark values.

## Applied

- **Type, three voices.** Instrument Serif speaks once per page ("Today", the trail name, "Archive"), in
  one weight. Instrument Sans works: rows, labels, prose. JetBrains Mono labels: elevations, counts,
  citations, source values. The serif never sits on a number; archive day pages use the weekday name.
- **Warm paper** `#f7f6f3`. Dark is the same paper at night (`#141312`), not an inversion.
- **Status is a glyph plus a word.** The glyphs are drawn here, and shape carries the meaning: check for
  dry, wave for muddy, asterisk for snow, slashed circle for closed, dashed ring for unknown. Colors are
  muted and secondary.
- **One accent.** Rust `#b0461f` appears only for "closed", the status that needs you.
- **Say it once.** Lines are grouped under a sans label ("Likely dry"), so rows don't repeat the word. The
  counts appear once, in the summary under the date.
- **Quiet lists.** There are no rule lines between rows. Hovering a row dims the others (140ms, ease-out).
- **No motion on load or scroll.** The page paints finished. The only transitions are hover color and
  opacity, and they respect `prefers-reduced-motion`.
- **One scene, receding.** A halftone ridgeline sits behind the title on day pages. Dots are the only
  ornament. Alternatives are rendered in `docs/screenshots/options/`: `ridge` (default), `wash` (a soft
  sage and morning-gold CSS wash), and `none`. Switch with `<body data-scene>` in `base.html`.
- **Checked at 1052×854 @2x and 390×844 @2x** (`scripts/screenshots.py`), with no horizontal overflow.

## Deliberate deviations

- **Oversized display.** "Today" is set at up to 9rem, bigger than Dervo's 48px hero. That's the one big type
  move the original brief asked for, and it matches the editorial saves in the library.
- **Five status colors.** The brief asked for one color per status. They're muted, small, and only on
  glyphs, never on text or backgrounds, so the page doesn't go rainbow.
