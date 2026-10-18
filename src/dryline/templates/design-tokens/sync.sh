#!/bin/sh
# Vendors a pinned copy of @brambach/design-tokens from the private
# design-taste repo into this project, and checks the copy hasn't drifted.
#
#   sh sync.sh --ref v0.1.0 --dest vendor/design-tokens   first install, or a bump
#   sh vendor/design-tokens/sync.sh                       re-sync the pinned ref
#   sh vendor/design-tokens/sync.sh --ref v0.2.0          bump
#   sh vendor/design-tokens/sync.sh --check               offline drift check for CI
#   sh vendor/design-tokens/sync.sh --outdated            is there a newer tag? (needs repo access)
#
# Fetching needs read access to the repo through git (SSH key, or HTTPS via
# `gh auth setup-git`). --check needs nothing, so it's safe in public CI.
# Set DESIGN_TASTE_REPO to fetch from another URL or a local clone.

set -eu

repo="${DESIGN_TASTE_REPO:-https://github.com/brambach/design-taste.git}"
mode=sync
ref=""
dest=""

die() { echo "design-tokens: $*" >&2; exit 1; }

while [ $# -gt 0 ]; do
  case "$1" in
    --ref) [ $# -ge 2 ] || die "--ref needs a value"; ref="$2"; shift 2 ;;
    --dest) [ $# -ge 2 ] || die "--dest needs a value"; dest="$2"; shift 2 ;;
    --check) mode=check; shift ;;
    --outdated) mode=outdated; shift ;;
    -h|--help) sed -n '2,15p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) die "unknown argument: $1 (try --help)" ;;
  esac
done

if [ -z "$dest" ]; then
  case "$0" in
    */sync.sh|sync.sh) dest=$(dirname "$0") ;;
    *) die "pass --dest <dir> (e.g. --dest vendor/design-tokens)" ;;
  esac
fi
[ -f "$dest/dev/build.mjs" ] && die "$dest is the source package in design-taste, not a vendored copy"

if command -v sha256sum >/dev/null 2>&1; then sha() { sha256sum "$@"; }
else sha() { shasum -a 256 "$@"; }
fi

file_list() { (cd "$1" && find . -type f ! -name SHA256SUMS | sed 's|^\./||' | LC_ALL=C sort); }
pinned() { sed -n "s/^$1=//p" "$dest/VERSION" 2>/dev/null; }

case "$mode" in
  check)
    [ -f "$dest/VERSION" ] && [ -f "$dest/SHA256SUMS" ] || die "$dest has no VERSION or SHA256SUMS. Run sync first."
    listed=$(sed 's/^[0-9a-f]*  //' "$dest/SHA256SUMS" | LC_ALL=C sort)
    present=$(file_list "$dest")
    if [ "$listed" != "$present" ]; then
      echo "design-tokens: files in $dest don't match SHA256SUMS:" >&2
      printf '%s\n' "$listed" > "${TMPDIR:-/tmp}/dt-listed.$$"
      printf '%s\n' "$present" > "${TMPDIR:-/tmp}/dt-present.$$"
      diff "${TMPDIR:-/tmp}/dt-listed.$$" "${TMPDIR:-/tmp}/dt-present.$$" >&2 || true
      rm -f "${TMPDIR:-/tmp}/dt-listed.$$" "${TMPDIR:-/tmp}/dt-present.$$"
      die "vendored tokens drifted. Don't edit them here; override in your own CSS, or re-run sync.sh."
    fi
    if ! (cd "$dest" && sha -c SHA256SUMS >/dev/null 2>&1); then
      (cd "$dest" && sha -c SHA256SUMS 2>/dev/null | grep -v ': OK$' >&2) || true
      die "vendored tokens drifted. Don't edit them here; override in your own CSS, or re-run sync.sh."
    fi
    echo "design-tokens: $dest matches $(pinned ref) ($(pinned commit | cut -c1-12))"
    ;;

  outdated)
    current=$(pinned ref)
    latest=$(git ls-remote --tags --refs "$repo" 'v*' | sed 's|.*refs/tags/||' | sort -V | tail -n 1)
    [ -n "$latest" ] || die "no v* tags found in $repo"
    if [ "$current" = "$latest" ]; then echo "design-tokens: $current is the latest"
    else echo "design-tokens: pinned ${current:-nothing}, latest is $latest. Run: sh $dest/sync.sh --ref $latest"; exit 1
    fi
    ;;

  sync)
    [ -n "$ref" ] || ref=$(pinned ref)
    [ -n "$ref" ] || die "pass --ref (a tag like v0.1.0)"
    if [ -d "$dest" ] && [ -n "$(ls -A "$dest")" ] && [ ! -f "$dest/VERSION" ]; then
      die "$dest exists and isn't a vendored copy. Pick an empty or new --dest."
    fi

    tmp=$(mktemp -d)
    trap 'rm -rf "$tmp"' EXIT INT TERM
    git -C "$tmp" init -q
    git -C "$tmp" remote add origin "$repo"
    git -C "$tmp" fetch -q --depth 1 --filter=blob:none origin "$ref" 2>/dev/null \
      || git -C "$tmp" fetch -q --depth 1 origin "$ref" \
      || die "couldn't fetch $ref from $repo. Check the tag exists and git can read the repo."
    commit=$(git -C "$tmp" rev-parse 'FETCH_HEAD^{commit}')
    git -C "$tmp" checkout -q FETCH_HEAD -- tokens 2>/dev/null || die "$ref has no tokens/ folder"
    src="$tmp/tokens"
    version=$(sed -n 's/^ *"version": *"\([^"]*\)".*/\1/p' "$src/package.json" | head -n 1)

    rm -rf "$dest"
    mkdir -p "$dest"
    cp -R "$src/." "$dest/"
    rm -rf "$dest/dev"
    {
      echo "ref=$ref"
      echo "commit=$commit"
      echo "version=$version"
      echo "source=github.com/brambach/design-taste tokens/"
    } > "$dest/VERSION"
    (cd "$dest" && file_list . | while IFS= read -r f; do sha "$f"; done) > "$tmp/SHA256SUMS"
    mv "$tmp/SHA256SUMS" "$dest/SHA256SUMS"
    echo "design-tokens: vendored v$version ($ref, $(echo "$commit" | cut -c1-12)) into $dest"
    ;;
esac


