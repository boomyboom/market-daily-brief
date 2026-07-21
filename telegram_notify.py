#!/usr/bin/env python3
"""Send the latest daily market brief to Telegram.

Reads TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID (and optional SITE_URL) from .env,
finds the most recent brief JSON, formats a concise summary, and pushes it.

Usage:
    python3 telegram_notify.py            # send latest brief
    python3 telegram_notify.py --date 2026-07-18
"""
import json
import os
import sys
import glob
import html
import urllib.request
import urllib.parse

ROOT = os.path.dirname(os.path.abspath(__file__))
BRIEFS_DIR = os.path.join(ROOT, "briefs")
TG_LIMIT = 4096


def load_env():
    env = {}
    path = os.path.join(ROOT, ".env")
    if os.path.exists(path):
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    for k in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "SITE_URL"):
        if os.environ.get(k):
            env[k] = os.environ[k]
    return env


def latest_brief_path(date=None):
    if date:
        p = os.path.join(BRIEFS_DIR, f"{date}.json")
        return p if os.path.exists(p) else None
    files = sorted(glob.glob(os.path.join(BRIEFS_DIR, "20*-*-*.json")))
    return files[-1] if files else None


def esc(s):
    return html.escape(str(s or ""))


def pct_num(s):
    m = "".join(c for c in str(s or "") if c in "0123456789.-")
    try:
        return float(m)
    except ValueError:
        return None


def indices_line(arr):
    parts = [f"{esc(i.get('name'))} {esc(i.get('change_pct'))}" for i in (arr or []) if i.get("name")]
    return " · ".join(parts)


def sector_summary(sectors):
    """Return (strong, weak) lists sorted by change_pct."""
    vals = [s for s in (sectors or []) if pct_num(s.get("change_pct")) is not None]
    vals.sort(key=lambda s: pct_num(s.get("change_pct")), reverse=True)
    strong = [s for s in vals[:3] if pct_num(s.get("change_pct")) > 0]
    weak = [s for s in reversed(vals[-3:]) if pct_num(s.get("change_pct")) < 0]
    return strong, weak


def sector_block(label, sectors):
    strong, weak = sector_summary(sectors)
    if not strong and not weak:
        return []
    line = [f"{label}"]
    if strong:
        line.append("  🟢 강세: " + ", ".join(f"{esc(s['name'])} {esc(s['change_pct'])}" for s in strong))
    if weak:
        line.append("  🔴 약세: " + ", ".join(f"{esc(s['name'])} {esc(s['change_pct'])}" for s in weak))
    return line


def format_message(brief, site_url=""):
    L = []
    L.append(f"📊 <b>오늘의 시장 브리핑</b> — {esc(brief.get('date',''))}")
    if brief.get("headline"):
        L.append(f"<i>{esc(brief['headline'])}</i>")
    L.append("")

    # 🇰🇷 한국장 (메인)
    kr = brief.get("kr", {}) or {}
    L.append("🇰🇷 <b>한국장</b>")
    if indices_line(kr.get("indices")):
        L.append("📈 " + indices_line(kr.get("indices")))
    if kr.get("preview"):
        L.append(esc(kr["preview"]))
    hot = kr.get("hot_stocks") or []
    if hot:
        L.append("<b>🔥 오늘의 화제 종목</b>")
        for s in hot[:6]:
            L.append(f"• {esc(s.get('name') or s.get('ticker'))} {esc(s.get('change_pct'))} — {esc(s.get('reason'))}")
    L.append("")

    # 📊 섹터 히트맵 요약
    sec = brief.get("sectors", {}) or {}
    sblock = []
    sblock += sector_block("🇰🇷 한국", sec.get("kr"))
    sblock += sector_block("🇺🇸 미국", sec.get("us"))
    if sblock:
        L.append("📊 <b>섹터 흐름</b>")
        L += sblock
        L.append("")

    # 💱 핵심 지표 (환율·금·코인)
    assets = brief.get("assets") or []
    if assets:
        L.append("💱 <b>환율·금·코인</b>")
        parts = []
        for a in assets:
            if not a.get("name"):
                continue
            pct = str(a.get("change_pct") or "").strip()
            tail = f" ({esc(pct)})" if pct else ""
            parts.append(f"{esc(a.get('name'))} {esc(a.get('value'))}{tail}")
        L.append(" · ".join(parts))
        L.append("")

    # 🇺🇸 미국장 (요약)
    us = brief.get("us", {}) or {}
    if us.get("recap") or indices_line(us.get("indices")):
        L.append("🇺🇸 <b>미국장</b> (밤사이 마감)")
        if indices_line(us.get("indices")):
            L.append("📈 " + indices_line(us.get("indices")))
        if us.get("recap"):
            L.append(esc(us["recap"]))
        L.append("")

    # 🎯 주목 종목
    spot = brief.get("spotlight") or []
    if spot:
        L.append("🎯 <b>주목 종목</b> (정보용)")
        for s in spot:
            lv = s.get("levels_watched", {}) or {}
            bits = []
            if lv.get("support"):
                bits.append(f"지지 {esc(lv['support'])}")
            if lv.get("resistance"):
                bits.append(f"저항 {esc(lv['resistance'])}")
            if lv.get("analyst_target_cited"):
                bits.append(f"목표가 {esc(lv['analyst_target_cited'])}")
            L.append(f"• <b>{esc(s.get('name') or s.get('ticker'))}</b> — {esc(s.get('thesis'))}")
            if bits:
                L.append(f"   ▸ {' / '.join(bits)}")
            if s.get("risk"):
                L.append(f"   ▸ 리스크: {esc(s['risk'])}")
        L.append("")

    if site_url:
        L.append("━━━━━━━━━━━━━━")
        L.append(f"📊 <a href=\"{esc(site_url)}\">데일리 브리프 사이트에서 전체 보기 →</a>")
    # 면책은 짧게 (전문은 웹·브리핑에). 길이 초과로 태그가 잘리는 것 방지.
    L.append("")
    L.append("<i>⚠️ 정보 제공용, 투자 권유 아님</i>")

    msg = "\n".join(L)
    if len(msg) > TG_LIMIT:
        # 태그가 중간에 잘리면 파싱 오류 → 안전한 지점까지 자르고 열린 태그 닫기
        cut = msg[: TG_LIMIT - 40]
        cut = cut[: cut.rfind("\n")] if "\n" in cut else cut  # 마지막 줄 경계에서 컷
        msg = cut.rstrip() + "\n…(생략) ℹ️ 정보 제공용"
    return msg


def send(token, chat_id, text):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = urllib.parse.urlencode({
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": "true",
    }).encode()
    with urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=30) as r:
        return json.loads(r.read().decode())


def main():
    date = None
    if "--date" in sys.argv:
        date = sys.argv[sys.argv.index("--date") + 1]

    env = load_env()
    token = env.get("TELEGRAM_BOT_TOKEN")
    chat_id = env.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("ERROR: TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set (.env)", file=sys.stderr)
        return 1

    path = latest_brief_path(date)
    if not path:
        print("ERROR: no brief JSON found", file=sys.stderr)
        return 1

    with open(path) as f:
        brief = json.load(f)

    text = format_message(brief, env.get("SITE_URL", ""))
    res = send(token, chat_id, text)
    if not res.get("ok"):
        print(f"ERROR: telegram send failed: {res}", file=sys.stderr)
        return 1
    print(f"OK: sent brief {brief.get('date')} to chat {chat_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
