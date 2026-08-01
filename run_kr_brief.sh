#!/usr/bin/env bash
# Korean market close brief, 19:00 KST. Covers what actually happened today in
# the KR session and why. The morning run stays US-led and looks back at this.
set -uo pipefail

REPO="/Applications/BoomyBoom"
cd "$REPO" || exit 1
if [ -f "$REPO/.env" ]; then
  set -a
  source "$REPO/.env"
  set +a
fi

PYTHON="${PYTHON_BIN:-/usr/bin/python3}"
GIT="${GIT_BIN:-/usr/bin/git}"
CLAUDE="${CLAUDE_BIN:-claude}"

mkdir -p "$REPO/logs"
TODAY="$(date +%Y-%m-%d)"
LOG="$REPO/logs/kr-$TODAY.log"
log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG"; }
send_alert() { bash "$REPO/send_telegram.sh" "$1" >>"$LOG" 2>&1 || true; }

log "===== KR close brief start ====="

# 주말이면 실행하지 않음 (월=1 ... 토=6, 일=7)
DOW="$(date +%u)"
if [ "$DOW" -ge 6 ]; then
  log "주말 ($TODAY) 이므로 건너뜀"; exit 0
fi

# 공휴일이면 건너뜀
if "$PYTHON" - "$TODAY" <<'PY'
import json, sys
today = sys.argv[1]
try:
    data = json.load(open("holidays_kr.json"))
    sys.exit(0 if today in data.get(today[:4], []) else 1)
except Exception:
    sys.exit(1)
PY
then
  log "한국 증시 휴장일 ($TODAY) 이므로 건너뜀"; exit 0
fi

BRIEF="$REPO/briefs/$TODAY-kr.json"
RUN_OUT="$REPO/logs/kr-claude-$TODAY.out"

if ! command -v "$CLAUDE" >/dev/null 2>&1 && [ ! -x "$CLAUDE" ]; then
  log "ERROR: claude CLI not found"
  send_alert "⚠️ 한국장 마감 브리핑 실패: claude CLI를 찾을 수 없어요 (.env CLAUDE_BIN 확인)"
  exit 1
fi

for attempt in 1 2; do
  log "invoking Claude Code headless… (시도 $attempt)"
  env -u TELEGRAM_BOT_TOKEN -u TELEGRAM_CHAT_ID -u TELEGRAM_APPROVE_BOT_TOKEN \
    -u THREADS_TOKEN -u MAIL_TO -u OBSIDIAN_VAULT \
    "$CLAUDE" -p "$(cat "$REPO/KR_BRIEF_PROMPT.md")" \
    --allowedTools "Task,Bash,WebSearch,WebFetch,Read,Write,Edit,Glob,Grep" >"$RUN_OUT" 2>&1
  log "claude exit: $?"
  cat "$RUN_OUT" >>"$LOG"
  [ -f "$BRIEF" ] && break
  if [ "$attempt" = "1" ]; then log "생성 안 됨, 60초 뒤 재시도"; sleep 60; fi
done

if [ ! -f "$BRIEF" ] && grep -qiE "Not logged in|Please run /login|Invalid API key|authentication_error|Unauthorized" "$RUN_OUT"; then
  log "DETECTED: Claude 로그인 문제"
  send_alert "🔒 Claude 로그인이 해제된 것 같아요.
오늘($TODAY) 한국장 마감 브리핑이 생성되지 않았습니다.
재로그인: $CLAUDE 실행 후 /login"
  exit 1
fi

if [ ! -f "$BRIEF" ]; then
  log "브리핑 파일 없음 (휴장 판단이거나 생성 실패)"
  log "===== KR close brief end ====="
  exit 0
fi

# 문장부호 정리
"$PYTHON" "$REPO/humanize_brief.py" "$BRIEF" >>"$LOG" 2>&1 || log "humanize 실패"

if ! "$PYTHON" "$REPO/validate_brief.py" "$BRIEF" >>"$LOG" 2>&1; then
  log "ERROR: 발행 전 검증 실패, 외부 발송 중단"
  send_alert "⚠️ 오늘($TODAY) 한국장 마감 브리핑이 품질 검증을 통과하지 못해 발행을 멈췄어요.
로그: $LOG"
  exit 1
fi
log "발행 전 검증 OK"

# 최종본을 올리고 아침 브리핑과 마감 브리핑을 함께 노출한다.
"$PYTHON" "$REPO/cleanup_old_briefs.py" >>"$LOG" 2>&1 || log "cleanup 실패"
PUBLISH_PATHS=("briefs/$TODAY-kr.json" "briefs/seen_urls.json" "briefs/manifest.json")
if "$GIT" add -- "${PUBLISH_PATHS[@]}" >>"$LOG" 2>&1; then
  if ! "$GIT" diff --cached --quiet -- "${PUBLISH_PATHS[@]}"; then
    if "$GIT" commit --only -m "kr brief: $TODAY (validated)" -- "${PUBLISH_PATHS[@]}" >>"$LOG" 2>&1; then
      log "최종 산출물 커밋 OK"
      "$GIT" push origin HEAD >>"$LOG" 2>&1 && log "GitHub Pages 반영 요청 OK" || log "GitHub push 실패"
    else
      log "최종 산출물 커밋 실패, push 생략"
    fi
  fi
else
  log "git add 실패"
fi

# Obsidian 주식뇌 기록
OBSIDIAN_FAILED=0
"$PYTHON" "$REPO/brief_to_obsidian.py" "$BRIEF" >>"$LOG" 2>&1 && log "obsidian 기록 OK" || { log "obsidian 기록 일부 또는 전체 실패"; OBSIDIAN_FAILED=1; }
# 위키 색인과 로그 갱신
"$PYTHON" "$REPO/wiki_tools.py" index >>"$LOG" 2>&1 || log "wiki index 갱신 실패"
"$PYTHON" "$REPO/wiki_tools.py" log "한국장 마감 $TODAY 기록" >>"$LOG" 2>&1 || log "wiki log 갱신 실패"

# 텔레그램 발송 (긴 메시지는 분할 발송됨)
"$PYTHON" "$REPO/telegram_notify.py" --file "$BRIEF" >>"$LOG" 2>&1 && log "telegram push OK" || log "telegram push 실패"

# 대시보드 형태 브리핑 메일 (텔레그램 나갈 때마다 함께)
"$PYTHON" "$REPO/send_brief_mail.py" "$BRIEF" >>"$LOG" 2>&1 && log "브리핑 메일 OK" || log "브리핑 메일 실패"

log "===== KR close brief end ====="
[ "$OBSIDIAN_FAILED" = "0" ] || exit 2
