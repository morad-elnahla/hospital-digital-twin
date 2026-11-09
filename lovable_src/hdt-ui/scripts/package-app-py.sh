#!/usr/bin/env bash
# Builds the UI package that the original app.py serves by itself:
#   dashboard.html  -> replaces app.py's dashboard.html
#   static/hdtui/   -> must REPLACE the whole old static/hdtui folder (never merge old + new chunks)
# Usage: scripts/package-app-py.sh <out-dir>
set -euo pipefail
OUT="${1:?out dir}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORK="$(mktemp -d)"
rsync -a --exclude node_modules --exclude dist --exclude .output --exclude .git "$ROOT/" "$WORK/"
ln -s "$ROOT/node_modules" "$WORK/node_modules"
(cd "$WORK" && HDT_PACKAGE=1 VITE_HASH_ROUTER=1 VITE_HDT_DIRECT=1 npx vite build >/dev/null)
bun "$ROOT/scripts/package-ssr.mjs" "$WORK/dist" > "$WORK/root.html" 2>/dev/null
rm -rf "$OUT" && mkdir -p "$OUT/static/hdtui"
cp -r "$WORK/dist/client/assets" "$OUT/static/hdtui/"
python3 - "$WORK/root.html" "$OUT" <<'PY'
import re, sys
src, out = sys.argv[1], sys.argv[2]
h = open(src, encoding="utf-8").read().replace('"/assets/', '"/static/hdtui/assets/')
n = [0]
def ext(m):  # app.py's CSP forbids inline scripts: move each one to its own file
    if "src=" in m.group(1): return m.group(0)
    i = n[0]; n[0] += 1
    open(f"{out}/static/hdtui/i{i}.js", "w", encoding="utf-8").write(m.group(2))
    return f'<script{m.group(1)} src="/static/hdtui/i{i}.js"></script>'
h = re.sub(r"<script([^>]*)>(.*?)</script>", ext, h, flags=re.S)
h = h.replace('<link rel="icon" href="/favicon.ico" type="image/x-icon"/>', "")
open(f"{out}/dashboard.html", "w", encoding="utf-8").write(h)
PY
# Fail if anything would load from a path app.py does not serve, or from data: (CSP).
if grep -q 'url(data:font' "$OUT"/static/hdtui/assets/*.css; then echo "inlined font found" >&2; exit 1; fi
if grep -o 'src="/assets/\|href="/assets/' "$OUT/dashboard.html"; then echo "bad asset path" >&2; exit 1; fi
rm -rf "$WORK"
echo "package ready: $OUT"
