# @brambach/design-tokens

Bryce's design tokens as CSS custom properties, with a JSON copy of the same
values. The source is `tokens/` in the private
[design-taste](https://github.com/brambach/design-taste) repo. Projects vendor
a pinned copy with `sync.sh` and import it from there, so there's one source
of truth and nobody hand-copies variables.

The values are Dervo's system cut down to a starter (see `../APPLY.md` and
`../built/`). If a project has its own tokens for something, its own win: set
them in the project's CSS, after these.

## Files

| File | What it is |
|---|---|
| `tokens.css` | The base. Light by default, `data-theme="dark"`, `data-theme="forest"`, reduced motion. Hand-written, the source for everything else. |
| `auto-dark.css` | Optional. Follows the OS dark setting while `<html>` has no `data-theme`. Generated. |
| `themes/warm-paper.css` | Optional. Arro's warm paper surfaces and inks (`built/arro.md`). Light only. |
| `accents/clay.css` | Optional. Arro's clay as the main action and the one accent. Light only. |
| `type/personal.css` | Optional. Sentient, Hanken Grotesk and IBM Plex Mono, the pair APPLY.md gives for personal work. |
| `tokens.json` | Every value above as data, for scripts, Python templates and TS. Generated. |
| `sync.sh` | Vendors a pinned copy into a project and checks it hasn't drifted. |
| `package.json` | Makes the vendored folder importable as `@brambach/design-tokens`. Not published anywhere. |

## Layering

Import in this order. Every layer only overrides base tokens, it never adds
new ones, so the token names below are the whole contract.

1. `tokens.css` (always)
2. `auto-dark.css` (if the site should follow the OS)
3. at most one file each from `themes/`, `accents/`, `type/`
4. the project's own CSS, which can override any token

Theme, accent and type layers are plain `:root` blocks. `data-theme="dark"`,
`data-theme="forest"` and `auto-dark.css` all have higher specificity, so dark
mode always falls back to the base dark values. Arro is light only, so there
are no dark values for warm paper or clay to invent.

Themes switch with an attribute on `<html>`: none (light, or the OS setting
with `auto-dark.css`), `data-theme="light"`, `data-theme="dark"`,
`data-theme="forest"`.

Which layers a project wants:

| Project | Surface | Layers |
|---|---|---|
| comehome | lost-pet page, Arro's warm register | `tokens.css`, `themes/warm-paper.css`, `accents/clay.css` |
| dryline | product surface, follows the OS | `tokens.css`, `auto-dark.css` |
| easeprint | product chrome, follows the OS | `tokens.css`, `auto-dark.css` |

## How projects get it, and why this way

All three consumers are public repos that deploy to Vercel or GitHub Pages,
and this repo is private. Anything that fetches at install or build time would
need a token with read access to a private repo stored in every public
project's CI and hosting settings. So the tokens are **vendored**: `sync.sh`
copies a pinned tag into the project, the copy is committed, and builds need
no network, no auth and no Node (the Python site works the same way).

| Option | Why not |
|---|---|
| Git dependency pinned to a tag | Every `npm install` on Vercel and in Actions needs a PAT for the private repo. Doesn't help the Python site. |
| GitHub Packages | Needs a token even to read, everywhere it installs. Doesn't help the Python site. |
| Public npm | Simplest install, but adds a publish step and an npm account. The tokens are already public in the consumer repos, so this is the upgrade path if vendoring gets annoying. |
| **Vendor with `sync.sh`** | **Chosen.** Zero auth at build time, works for any stack. The cost: a committed copy, and bumping is a deliberate step on a machine that can read this repo. |

What keeps the copy honest:

- `VERSION` records the tag and the exact commit it came from.
- `SHA256SUMS` covers every vendored file. `sync.sh --check` fails if any file
  was edited, added or removed. It's offline, so it runs in public CI.
- `sync.sh --outdated` says whether a newer tag exists. It needs repo access,
  so run it locally rather than in public CI.

Fetching uses plain git, so it needs read access to this repo: an SSH key, or
`gh auth login` followed by `gh auth setup-git` for HTTPS.

## Install

Releases are git tags on this repo (`v0.1.0`). The first install fetches
`sync.sh` itself through `gh`; after that the vendored copy updates itself.

### Next.js (App Router)

```sh
gh api 'repos/brambach/design-taste/contents/tokens/sync.sh?ref=v0.1.0' -H 'Accept: application/vnd.github.raw' \
  | sh -s -- --ref v0.1.0 --dest vendor/design-tokens
npm install ./vendor/design-tokens
npm install @fontsource/instrument-serif @fontsource/instrument-sans @fontsource/jetbrains-mono
```

With pnpm, the second line is `pnpm add @brambach/design-tokens@link:./vendor/design-tokens`.

`app/layout.tsx`, before the app's own CSS:

```tsx
import "@fontsource/instrument-serif/400.css";
import "@fontsource/instrument-serif/400-italic.css";
import "@fontsource/instrument-sans/400.css";
import "@fontsource/instrument-sans/500.css";
import "@fontsource/instrument-sans/600.css";
import "@fontsource/jetbrains-mono/400.css";
import "@fontsource/jetbrains-mono/500.css";
import "@brambach/design-tokens/tokens.css";
import "@brambach/design-tokens/themes/warm-paper.css"; // comehome only
import "@brambach/design-tokens/accents/clay.css";      // comehome only
import "./globals.css";
```

The `@fontsource` packages register the exact family names the tokens use.
If you'd rather use `next/font`, its generated family names won't match, so
point the tokens at its variables in `globals.css`:
`:root { --font-display: var(--font-instrument-serif), Georgia, serif; }`.

In TS, the values are importable too:
`import tokens from "@brambach/design-tokens/tokens.json";` then
`tokens.modes.light.paper` is `"#f7f6f3"`.

### Astro

```sh
gh api 'repos/brambach/design-taste/contents/tokens/sync.sh?ref=v0.1.0' -H 'Accept: application/vnd.github.raw' \
  | sh -s -- --ref v0.1.0 --dest vendor/design-tokens
pnpm add @brambach/design-tokens@link:./vendor/design-tokens
```

With npm, the second line is `npm install ./vendor/design-tokens`.

At the top of `src/styles/global.css`, after the font imports:

```css
@import "@brambach/design-tokens/tokens.css";
@import "@brambach/design-tokens/auto-dark.css";
```

Or in a layout's frontmatter: `import "@brambach/design-tokens/tokens.css";`.

If the project uses `@fontsource-variable/instrument-sans`, that package
registers the family as "Instrument Sans Variable", so add
`:root { --font-text: "Instrument Sans Variable", "Instrument Sans", system-ui, sans-serif; }`
in the project's CSS, or switch to `@fontsource/instrument-sans`.

### Python-rendered static site (Jinja or similar)

Vendor next to the templates so the package ships it:

```sh
gh api 'repos/brambach/design-taste/contents/tokens/sync.sh?ref=v0.1.0' -H 'Accept: application/vnd.github.raw' \
  | sh -s -- --ref v0.1.0 --dest src/dryline/templates/design-tokens
```

Copy the CSS into the output in the build step:

```python
import shutil
src = templates / "design-tokens"
shutil.copytree(src, out / "design-tokens", ignore=shutil.ignore_patterns("*.sh", "*.md", "package.json", "VERSION", "SHA256SUMS"))
```

Link it before the site's own stylesheet in the base template:

```html
<link rel="stylesheet" href="{{ root }}design-tokens/tokens.css">
<link rel="stylesheet" href="{{ root }}design-tokens/auto-dark.css">
<link rel="stylesheet" href="{{ root }}style.css">
```

Values for templates, like `theme-color`, come from the JSON:

```python
import json
tokens = json.loads((templates / "design-tokens" / "tokens.json").read_text())
tokens["modes"]["light"]["paper"]  # "#f7f6f3"
tokens["modes"]["dark"]["paper"]   # "#141312"
```

Fonts stay self-hosted in the project, registered with the family names the
tokens use: "Instrument Serif", "Instrument Sans", "JetBrains Mono".

### CI drift check

GitHub Actions, in any workflow that runs on push:

```yaml
- run: sh vendor/design-tokens/sync.sh --check
```

On Vercel, make it part of the build in `package.json`:

```json
"scripts": { "prebuild": "sh vendor/design-tokens/sync.sh --check" }
```

### Bumping

```sh
sh vendor/design-tokens/sync.sh --outdated
sh vendor/design-tokens/sync.sh --ref v0.2.0
npm install   # or pnpm install, so node_modules picks up the new copy
```

Commit the vendored folder with the bump.

## Token names

CSS name is `--` plus the key; `tokens.json` uses the key without `--`.

- **Type families:** `--font-display`, `--font-text`, `--font-mono`
- **Type sizes:** `--fs-caption` (12), `--fs-small` (13), `--fs-body` (14), `--fs-read` (15), `--fs-title` (17), `--fs-h2` (26), `--fs-h1` (34), `--fs-hero` (48)
- **Line heights:** `--lh-tight`, `--lh-ui`, `--lh-read`
- **Surfaces:** `--paper`, `--canvas`, `--raised`, `--sunk`
- **Ink and lines:** `--ink`, `--ink-2`, `--muted`, `--faint`, `--line`, `--line-strong`
- **Meaning:** `--primary`, `--on-primary`, `--done`, `--done-wash`, `--running`, `--running-wash`, `--accent`, `--accent-wash`, `--on-accent`, `--focus`
- **Space:** `--s1` (4) `--s2` (8) `--s3` (12) `--s4` (16) `--s5` (24) `--s6` (32) `--s7` (48) `--s8` (64) `--s9` (96) `--s10` (128)
- **Radii:** `--r1` (6), `--r2` (10), `--r3` (14), `--r-pill`
- **Depth:** `--card-edge`, `--lift`, `--float`, `--btn-lit`, `--btn-pressed`, `--glass`, `--glass-blur`
- **Easing:** `--ease-out`, `--ease-in`, `--ease-move`, `--ease-signature`
- **Durations:** `--dur-instant` (80ms), `--dur-fast` (140ms), `--dur-calm` (220ms), `--dur-move` (320ms), `--dur-arrive` (480ms), `--dur-loop` (1.2s)

Overridden by each layer:

- `data-theme="dark"`, `data-theme="forest"`, `auto-dark.css`: the surfaces, inks, lines, meaning colors except `--focus`, and the depth tokens except `--glass-blur`, plus `color-scheme`
- reduced motion: `--dur-instant`, `--dur-fast`, `--dur-calm`, `--dur-move`, `--dur-arrive` go to 0ms
- `themes/warm-paper.css`: `--paper`, `--raised`, `--sunk`, `--ink`, `--ink-2`, `--muted`, `--faint`, `--done`, `--done-wash`, `--lift`
- `accents/clay.css`: `--primary`, `--accent`
- `type/personal.css`: `--font-display`, `--font-text`, `--font-mono`

## Changing the tokens

In this repo, not in a vendored copy:

1. Edit `tokens.css` or a layer. Record the reason in the matching `built/`
   note; the tokens follow the taste, not the other way round.
2. Bump `version` in `package.json` and the version in the `tokens.css` header.
3. Run `node tokens/dev/build.mjs` to regenerate `tokens.json` and
   `auto-dark.css`, then `npm test --prefix tokens`. The build checks that
   layers only override base tokens, every `var()` resolves, dark and forest
   cover the same tokens, key text pairs pass WCAG contrast, and this README
   lists every token.
4. Merge, then tag the merge commit: `git tag v0.2.0 && git push origin v0.2.0`.


