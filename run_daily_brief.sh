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
# 텔레그램 경고 발송 (문제 발생 시)
send_alert() { bash "$REPO/send_telegram.sh" "$1" >>"$LOG" 2>&1 && log "alert sent" || log "alert send FAILED"; }
ALERTED=0

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
RUN_OUT="$REPO/logs/claude-$TODAY.out"
if ! command -v "$CLAUDE" >/dev/null 2>&1 && [ ! -x "$CLAUDE" ]; then
  log "ERROR: claude CLI not found (set CLAUDE_BIN in .env)."
  send_alert "⚠️ BoomyBoom 브리핑 실패
claude CLI를 찾을 수 없어요. .env의 CLAUDE_BIN 경로를 확인해주세요."
  ALERTED=1
else
  log "invoking Claude Code headless…"
  "$CLAUDE" -p "$(cat "$REPO/BRIEF_PROMPT.md")" \
    --allowedTools "Task,Bash,WebSearch,WebFetch,Read,Write,Edit,Glob,Grep" \
    >"$RUN_OUT" 2>&1
  log "claude exit status: $?"
  cat "$RUN_OUT" >>"$LOG"

  # 로그인/인증 해제 감지 → 텔레그램 경고
  if grep -qiE "Not logged in|Please run /login|Invalid API key|authentication_error|Unauthorized|please log in" "$RUN_OUT"; then
    log "DETECTED: Claude 로그인/인증 문제"
    send_alert "🔒 Claude 로그인이 해제된 것 같아요.
오늘($TODAY) 시장 브리핑이 생성되지 않았습니다.

터미널에서 재로그인 해주세요:
  $CLAUDE
→ 실행한 뒤 /login 입력

재로그인 후 수동 실행: bash $REPO/run_daily_brief.sh"
    ALERTED=1
  fi
fi

# ---- safety: refresh manifest even if claude skipped it ----
"$PYTHON" "$REPO/cleanup_old_briefs.py" >>"$LOG" 2>&1 || log "cleanup failed"

# ---- Obsidian 제2의 뇌 기록 ----
if [ -f "$REPO/briefs/$TODAY.json" ]; then
  "$PYTHON" "$REPO/brief_to_obsidian.py" "$REPO/briefs/$TODAY.json" >>"$LOG" 2>&1 && log "obsidian 기록 OK" || log "obsidian export 실패"
fi

# ---- record git state after ----
REV_AFTER="$("$GIT" rev-parse HEAD 2>/dev/null || echo none)"

# ---- safety net: 오늘 브리핑이 아예 안 만들어졌으면 경고 (로그인 외 다른 실패) ----
if [ ! -f "$REPO/briefs/$TODAY.json" ] && [ "$ALERTED" = "0" ]; then
  log "WARN: 오늘($TODAY) 브리핑 파일이 생성되지 않음"
  send_alert "⚠️ BoomyBoom: 오늘($TODAY) 시장 브리핑이 생성되지 않았어요.
로그를 확인해주세요: $REPO/logs/$TODAY.log"
  ALERTED=1
fi

# ---- notify only if content changed (or NOTIFY_ALWAYS=1) ----
if [ "$REV_BEFORE" != "$REV_AFTER" ] || [ "${NOTIFY_ALWAYS:-0}" = "1" ]; then
  log "changes detected → sending Telegram push"
  "$PYTHON" "$REPO/telegram_notify.py" >>"$LOG" 2>&1 && log "telegram push OK" || log "telegram push FAILED"
else
  log "no changes ($REV_BEFORE) — skipping Telegram push"
fi

log "===== daily brief run end ====="
