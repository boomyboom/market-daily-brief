#!/usr/bin/env bash
# Daily market brief runner — invoked by launchd at 08:00 KST.
# Invokes Claude Code headless to generate/update the brief, then pushes to Telegram.
set -uo pipefail

REPO="/Applications/BoomyBoom"
cd "$REPO" || exit 1

# ---- load .env (for CLAUDE_BIN, PATH additions, tokens) ----
if [ -f "$REPO/.env" ]; then
  set -a; source "$REPO/.env"; set +a
fi

# ---- resolve binaries (launchd has a minimal PATH) ----
PYTHON="${PYTHON_BIN:-/usr/bin/python3}"
GIT="${GIT_BIN:-/usr/bin/git}"
# CLAUDE_BIN must be set in .env, e.g. CLAUDE_BIN=/Users/you/.local/bin/claude
CLAUDE="${CLAUDE_BIN:-claude}"

# ---- logging ----
mkdir -p "$REPO/logs"
TODAY="$(date +%Y-%m-%d)"
LOG="$REPO/logs/$TODAY.log"
log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG"; }

log "===== daily brief run start ====="

# ---- skip Sunday (일요일은 월요일 브리핑에 합쳐서 처리) ----
# date +%u : 월=1 … 일=7.  RUN_SUNDAY=1 로 강제 실행 가능.
if [ "$(date +%u)" = "7" ] && [ "${RUN_SUNDAY:-0}" != "1" ]; then
  log "Sunday — skipping (covered by Monday's brief)."
  exit 0
fi

# ---- optional: skip Korean market holidays (US recap still useful, so off by default) ----
# SKIP_HOLIDAYS=1 in .env to enable.
if [ "${SKIP_HOLIDAYS:-0}" = "1" ]; then
  if "$PYTHON" - "$TODAY" <<'PY'
import json, sys, os
today = sys.argv[1]
p = os.path.join(os.path.dirname(os.path.abspath(__file__)) if False else ".", "holidays_kr.json")
try:
    data = json.load(open("holidays_kr.json"))
    year = today[:4]
    sys.exit(0 if today in data.get(year, []) else 1)
except Exception:
    sys.exit(1)
PY
  then
    log "KR market holiday ($TODAY) — skipping."
    exit 0
  fi
fi

# ---- record git state before ----
REV_BEFORE="$("$GIT" rev-parse HEAD 2>/dev/null || echo none)"

# ---- invoke Claude Code headless ----
if ! command -v "$CLAUDE" >/dev/null 2>&1 && [ ! -x "$CLAUDE" ]; then
  log "ERROR: claude CLI not found (set CLAUDE_BIN in .env). Aborting generation."
else
  log "invoking Claude Code headless…"
  "$CLAUDE" -p "$(cat "$REPO/BRIEF_PROMPT.md")" \
    --allowedTools "Task,Bash,WebSearch,WebFetch,Read,Write,Edit,Glob,Grep" \
    >>"$LOG" 2>&1
  log "claude exit status: $?"
fi

# ---- safety: refresh manifest even if claude skipped it ----
"$PYTHON" "$REPO/cleanup_old_briefs.py" >>"$LOG" 2>&1 || log "cleanup failed"

# ---- record git state after ----
REV_AFTER="$("$GIT" rev-parse HEAD 2>/dev/null || echo none)"

# ---- notify only if content changed (or NOTIFY_ALWAYS=1) ----
if [ "$REV_BEFORE" != "$REV_AFTER" ] || [ "${NOTIFY_ALWAYS:-0}" = "1" ]; then
  log "changes detected → sending Telegram push"
  "$PYTHON" "$REPO/telegram_notify.py" >>"$LOG" 2>&1 && log "telegram push OK" || log "telegram push FAILED"
else
  log "no changes ($REV_BEFORE) — skipping Telegram push"
fi

log "===== daily brief run end ====="
