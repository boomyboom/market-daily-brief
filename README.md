# BoomyBoom · Daily Market Brief

매일 아침 **KST 08:00**에 전 세계 뉴스·시장 데이터를 종합해서
- 📊 **웹 대시보드**(`index.html`, GitHub Pages) 업데이트
- 📲 **텔레그램** 그룹으로 요약 푸시

를 자동으로 수행하는 개인용 시장 인텔리전스 브리핑.

> ⚠️ **정보 제공용**입니다. 투자 권유·매수/매도 추천이 아니며, 모든 투자 판단과 책임은 본인에게 있습니다.

## 대상 시장
- 🇺🇸 미국장 (S&P 500 / 나스닥) — 밤사이 마감 리뷰
- 🇰🇷 한국장 (코스피 / 코스닥) — 오늘 개장 프리뷰

## 구조
| 파일 | 역할 |
|---|---|
| `run_daily_brief.sh` | launchd가 08:00에 실행. Claude Code headless 호출 → 생성 → 알림 |
| `BRIEF_PROMPT.md` | headless Claude에게 주는 생성 지침 (JSON 스키마 포함) |
| `BRIEFING_GUIDE.md` | 수집 대상·중복 방지·Spotlight 규칙·면책 고지 |
| `watchlist.json` | 관심 종목 (자유 편집) |
| `briefs/YYYY-MM-DD.json` | 그날의 브리핑 데이터 (30일 후 자동 삭제) |
| `briefs/manifest.json` | 브리핑 날짜 인덱스 (웹이 읽음) |
| `index.html` | 웹 대시보드 (manifest → 최신 브리핑 렌더) |
| `telegram_notify.py` | 최신 브리핑을 텔레그램으로 푸시 |
| `cleanup_old_briefs.py` | 30일 지난 브리핑 삭제 + manifest 재생성 |
| `com.boomyboom.marketbrief.plist` | launchd 스케줄 (08:00 KST) |
| `.env` | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `CLAUDE_BIN` 등 (git 제외) |

## 설정 (.env)
```
TELEGRAM_BOT_TOKEN=...        # BotFather 발급
TELEGRAM_CHAT_ID=...          # 대상 그룹/채널 ID
CLAUDE_BIN=/path/to/claude    # Claude Code CLI 절대경로 (launchd용)
SITE_URL=                     # (선택) GitHub Pages URL — 텔레그램에 링크 첨부
# SKIP_HOLIDAYS=1             # (선택) 한국 증시 휴장일 건너뛰기
# NOTIFY_ALWAYS=1            # (선택) 변경 없어도 매일 푸시
```

## 수동 실행 / 테스트
```bash
# 텔레그램 푸시만 테스트
python3 telegram_notify.py

# manifest 재생성
python3 cleanup_old_briefs.py

# 전체 파이프라인 (claude CLI 필요)
bash run_daily_brief.sh

# 웹 대시보드 로컬 확인
python3 -m http.server 8787   # → http://127.0.0.1:8787
```

## 스케줄러 등록 (launchd)
```bash
cp com.boomyboom.marketbrief.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.boomyboom.marketbrief.plist
# 해제: launchctl unload ~/Library/LaunchAgents/com.boomyboom.marketbrief.plist
```
