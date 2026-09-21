#!/usr/bin/env bash
# Raise the version and tag it. GitHub builds and publishes the rest.
#
#   ./scripts/release.sh patch      1.2.3 -> 1.2.4   a fix
#   ./scripts/release.sh minor      1.2.3 -> 1.3.0   something new
#   ./scripts/release.sh major      1.2.3 -> 2.0.0   something that breaks
#   ./scripts/release.sh 2.5.0      that number, whatever is there now
#
# The same three words the Release button in the Actions tab offers, because
# that button runs this script. Neither is the real one; use whichever you are
# in front of.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INIT="$ROOT/dikte/__init__.py"
BUMP="${1:-}"
YES=0
PUSH=1
for arg in "${@:2}"; do
  case "$arg" in
    --yes|-y)   YES=1 ;;
    --no-push)  PUSH=0 ;;
    *) echo "unknown option: $arg" >&2; exit 2 ;;
  esac
done

die() { printf 'release: %s\n' "$1" >&2; exit 1; }

CURRENT="$(sed -n 's/^__version__ = "\(.*\)"$/\1/p' "$INIT")"
[[ -n "$CURRENT" ]] || die "no __version__ in dikte/__init__.py"
IFS=. read -r major minor patch <<<"$CURRENT"

case "$BUMP" in
  major) NEXT="$((major + 1)).0.0" ;;
  minor) NEXT="$major.$((minor + 1)).0" ;;
  patch) NEXT="$major.$minor.$((patch + 1))" ;;
  [0-9]*.[0-9]*.[0-9]*) NEXT="$BUMP" ;;
  *) die "say major, minor, patch, or a number like 2.5.0" ;;
esac
TAG="v$NEXT"

cd "$ROOT"
# A release is built from what is tagged, so anything not committed would not
# be in it, and the tag would name a tree that never existed anywhere.
[[ -z "$(git status --porcelain)" ]] || die "commit or stash your changes first"
git rev-parse -q --verify "refs/tags/$TAG" >/dev/null && die "$TAG already exists"

if [[ $YES == 0 ]]; then
  printf '  %s -> %s, tagged %s' "$CURRENT" "$NEXT" "$TAG"
  [[ $PUSH == 1 ]] && printf ', and pushed to %s' "$(git rev-parse --abbrev-ref HEAD)"
  printf '\n  Enter to go ahead, Ctrl-C to stop. '
  read -r _
fi

# The one line, rewritten in place. A .bak and then delete it, because the BSD
# sed on a Mac and the GNU one on Linux disagree about what -i on its own means.
sed -i.bak "s/^__version__ = \".*\"$/__version__ = \"$NEXT\"/" "$INIT"
rm -f "$INIT.bak"

git add "$INIT"
git commit -q -m "Dikte $NEXT"
git tag -a "$TAG" -m "Dikte $NEXT"

if [[ $PUSH == 1 ]]; then
  git push -q origin HEAD "$TAG"
  echo "  Pushed $TAG. Watch it build: gh run watch"
else
  echo "  Tagged $TAG. Push it when you are ready: git push origin HEAD $TAG"
fi
