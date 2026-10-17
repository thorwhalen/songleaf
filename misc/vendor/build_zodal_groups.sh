#!/usr/bin/env bash
# Rebuild songleaf/data/web/vendor/zodal-groups.{js,css}: the part of zodal-groups the page
# uses (the model, its snapshot, the vanilla tree / tag input / tag menu), bundled as one ES
# module with zod, so the page needs no build step and no CDN at run time.
#
#   misc/vendor/build_zodal_groups.sh [REF]     # REF: a zodal-groups commit or tag (default below)
#
# Needs git, node and npm. Builds in a temporary directory; touches nothing but the two
# vendored files. Once zodal-groups >= 0.2.0 is on npm, build from the npm packages instead.
set -euo pipefail
REF="${1:-59f8688}"   # i2mint/zodal-groups, the commit the vendored files were built from
REPO="https://github.com/i2mint/zodal-groups.git"
HERE="$(cd "$(dirname "$0")/../.." && pwd)"
OUT="$HERE/songleaf/data/web/vendor"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

git clone --quiet "$REPO" "$WORK/src"
git -C "$WORK/src" checkout --quiet "$REF"
cd "$WORK"
npm init -y >/dev/null
npm install --silent --no-audit --no-fund esbuild@0.25 zod@4
cat > entry.js <<'JS'
// What the songleaf page uses from zodal-groups: the model, its snapshot, three renderers.
export { defineGroups, toSnapshot } from "@zodal/groups-core";
export { renderTree, renderTagInput, renderTagMenu } from "@zodal/groups-ui-vanilla";
JS
P="$WORK/src/packages"
node_modules/.bin/esbuild entry.js --bundle --format=esm --minify --target=es2020 --legal-comments=none \
  --alias:@zodal/groups-core="$P/groups-core/src/index.ts" \
  --alias:@zodal/groups-ui="$P/groups-ui/src/index.ts" \
  --alias:@zodal/groups-ui-vanilla="$P/groups-ui-vanilla/src/index.ts" \
  --outfile="$OUT/zodal-groups.js"
cp "$P/groups-ui-vanilla/src/styles.css" "$OUT/zodal-groups.css"
echo "Built from zodal-groups $REF ($(git -C "$WORK/src" rev-parse --short HEAD)) into $OUT"
