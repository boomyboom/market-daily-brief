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
from datetime import datetime

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
    # environment overrides .env
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


def format_message(brief, site_url=""):
    lines = []
    date = brief.get("date", "")
    lines.append(f"📊 <b>오늘의 시장 브리핑</b> — {esc(date)}")
    if brief.get("headline"):
        lines.append(f"<i>{esc(brief['headline'])}</i>")
    lines.append("")

    macro = brief.get("macro", {})
    if macro.get("us_close"):
        lines.append(f"🌙 <b>미국장</b>: {esc(macro['us_close'])}")
    if macro.get("kr_preview"):
        lines.append(f"🇰🇷 <b>한국장 프리뷰</b>: {esc(macro['kr_preview'])}")
    idx = macro.get("indices") or []
    if idx:
        parts = [f"{esc(i.get('name'))} {esc(i.get('change_pct'))}" for i in idx if i.get("name")]
        if parts:
            lines.append("📈 " + " · ".join(parts))
    lines.append("")

    themes = brief.get("top_themes") or []
    if themes:
        lines.append("🔥 <b>주도 테마</b>")
        for t in themes[:4]:
            tk = ", ".join(t.get("tickers", [])[:4])
            tail = f" ({esc(tk)})" if tk else ""
            lines.append(f"• {esc(t.get('theme'))}{tail}")
        lines.append("")

    movers = brief.get("movers") or []
    if movers:
        lines.append("⚡ <b>주요 급등락</b>")
        for m in movers[:5]:
            lines.append(f"• {esc(m.get('name') or m.get('ticker'))} {esc(m.get('change_pct'))} — {esc(m.get('reason'))}")
        lines.append("")

    spot = brief.get("spotlight") or []
    if spot:
        lines.append("🎯 <b>주목 종목</b> (정보용)")
        for s in spot:
            name = esc(s.get("name") or s.get("ticker"))
            lv = s.get("levels_watched", {}) or {}
            level_bits = []
            if lv.get("support"):
                level_bits.append(f"지지 {esc(lv['support'])}")
            if lv.get("resistance"):
                level_bits.append(f"저항 {esc(lv['resistance'])}")
            if lv.get("analyst_target_cited"):
                level_bits.append(f"목표가 {esc(lv['analyst_target_cited'])}")
            lines.append(f"• <b>{name}</b> — {esc(s.get('thesis'))}")
            if level_bits:
                lines.append(f"   ▸ {' / '.join(level_bits)}")
            if s.get("risk"):
                lines.append(f"   ▸ 리스크: {esc(s['risk'])}")
        lines.append("")

    if site_url:
        lines.append(f"🔗 <a href=\"{esc(site_url)}\">전체 브리핑 보기</a>")
    if brief.get("disclaimer"):
        lines.append("")
        lines.append(f"<i>{esc(brief['disclaimer'])}</i>")

    msg = "\n".join(lines)
    if len(msg) > TG_LIMIT:
        msg = msg[: TG_LIMIT - 20].rstrip() + "\n…(생략)"
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
