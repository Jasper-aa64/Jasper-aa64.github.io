#!/bin/bash
# watch-deploy.sh
# Local preview + auto build+push on every save.
# Usage: ./scripts/watch-deploy.sh
#
# What it does:
#   - Starts hugo server on :1313 for instant local preview
#   - Watches static/css/, layouts/, content/ for changes
#   - On any change: hugo --minify → git add → commit → push
#
# You see the result on localhost:1313 immediately (no delay).
# GitHub Pages picks it up ~60s later in the background.

set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_DIR"

# ── start hugo dev server ──────────────────────────────────────────────────
echo "▶ Starting Hugo server on http://localhost:1313 ..."
hugo server --disableFastRender --port 1313 &
HUGO_PID=$!

cleanup() {
  echo ""
  echo "▶ Stopping Hugo server..."
  kill "$HUGO_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

# ── deploy function ────────────────────────────────────────────────────────
deploy() {
  local changed_file="$1"
  echo ""
  echo "── change detected: $changed_file ──"

  echo "▶ Building..."
  hugo --minify --quiet

  if [[ -z "$(git status --porcelain)" ]]; then
    echo "▶ Nothing new to commit."
    return
  fi

  local msg="Auto-deploy: $(date '+%Y-%m-%d %H:%M') — ${changed_file##*/}"
  git add -A
  git commit -m "$msg"
  git push origin main
  echo "✓ Pushed: $msg"
}

# ── watch loop ─────────────────────────────────────────────────────────────
echo "▶ Watching for changes (Ctrl+C to stop)..."
echo ""

# Use fswatch if available, otherwise fall back to polling
if command -v fswatch &>/dev/null; then
  fswatch -r \
    --event Created --event Updated --event Removed \
    --exclude '\.git' --exclude 'docs/' --exclude 'public/' \
    static/css layouts content \
  | while read -r changed; do
      sleep 0.5   # debounce: wait for editor to finish writing
      deploy "$changed"
    done
else
  echo "  (fswatch not found — falling back to 5s polling)"
  echo "  Install with: brew install fswatch"
  echo ""
  LAST=""
  while true; do
    # fingerprint: mtimes of watched files
    CURRENT=$(find static/css layouts content -type f | sort | xargs stat -f "%m" 2>/dev/null | md5)
    if [[ "$CURRENT" != "$LAST" ]] && [[ -n "$LAST" ]]; then
      deploy "file change"
    fi
    LAST="$CURRENT"
    sleep 5
  done
fi
