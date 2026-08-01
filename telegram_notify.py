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
import time
import html
import re
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
    files = [f for f in sorted(glob.glob(os.path.join(BRIEFS_DIR, "20*-*-*.json")))
             if not f.endswith("-kr.json")]
    return files[-1] if files else None


def esc(s):
    return html.escape(str(s or ""))


def humanize(t):
    """Drop AI-tell punctuation the owner asked us to avoid (older briefs still have it)."""
    import re
    t = re.sub(r"[ \t]*[·・][ \t]*", ", ", t)
    t = re.sub(r"[ \t]*[—–][ \t]*", ", ", t)
    t = re.sub(r"(,[ \t]*){2,}", ", ", t)
    return t


def pct_num(s):
    import re
    m = re.search(r"^[^0-9+\-]*([+\-]?\d+(?:\.\d+)?)", str(s or "").strip())
    try:
        return float(m.group(1)) if m else None
    except (ValueError, AttributeError):
        return None


def indices_line(arr):
    parts = [f"{esc(i.get('name'))} {esc(i.get('change_pct'))}" for i in (arr or []) if i.get("name")]
    return ", ".join(parts)


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
    title = "🇰🇷 <b>한국장 마감 브리핑</b>" if brief.get("session") == "kr_close" else "📊 <b>오늘의 시장 브리핑</b>"
    L.append(f"{title} {esc(brief.get('date',''))}")
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
            L.append(f"• {esc(s.get('name') or s.get('ticker'))} {esc(s.get('change_pct'))}: {esc(s.get('reason'))}")
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

    # 💱 핵심 지표 (환율, 금, 코인)
    assets = brief.get("assets") or []
    if assets:
        L.append("💱 <b>환율, 금, 코인</b>")
        parts = []
        for a in assets:
            if not a.get("name"):
                continue
            pct = str(a.get("change_pct") or "").strip()
            tail = f" ({esc(pct)})" if pct else ""
            parts.append(f"{esc(a.get('name'))} {esc(a.get('value'))}{tail}")
        L.append(", ".join(parts))
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
            L.append(f"• <b>{esc(s.get('name') or s.get('ticker'))}</b>: {esc(s.get('thesis'))}")
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

    return humanize("\n".join(L))


def split_message(msg, limit=TG_LIMIT):
    """Split at line boundaries so nothing is dropped and no HTML tag is cut."""
    if len(msg) <= limit:
        return [msg]

    def split_long_line(line, room):
        if len(line) <= room:
            return [line]
        # A single pathological HTML line can otherwise be cut inside <b> or <a>.
        # For such lines only, preserve all visible text and drop formatting.
        line = esc(html.unescape(re.sub(r"<[^>]+>", "", line)))
        inner_room = max(1, room)
        chunks = []
        while len(line) > inner_room:
            cut = line.rfind(" ", 0, inner_room + 1)
            if cut < inner_room // 2:
                cut = inner_room
            # Do not leave a partial HTML entity at the boundary.
            amp = line.rfind("&", 0, cut)
            semi = line.rfind(";", 0, cut)
            if amp > semi and amp > 0:
                cut = amp
            chunks.append(line[:cut].rstrip())
            line = line[cut:].lstrip()
        if line:
            chunks.append(line)
        return chunks

    parts, cur = [], []
    lines = []
    for line in msg.split("\n"):
        lines.extend(split_long_line(line, limit - 40))
    for line in lines:
        candidate = ("\n".join(cur + [line])) if cur else line
        if len(candidate) > limit - 20 and cur:
            parts.append("\n".join(cur))
            cur = [line]
        else:
            cur.append(line)
    if cur:
        parts.append("\n".join(cur))
    total = len(parts)
    return [f"{p}\n\n<i>({i}/{total})</i>" for i, p in enumerate(parts, 1)]


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
    date, path = None, None
    if "--date" in sys.argv:
        date = sys.argv[sys.argv.index("--date") + 1]
    if "--file" in sys.argv:
        path = sys.argv[sys.argv.index("--file") + 1]

    env = load_env()
    token = env.get("TELEGRAM_BOT_TOKEN")
    chat_id = env.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("ERROR: TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set (.env)", file=sys.stderr)
        return 1

    if not path:
        path = latest_brief_path(date)
    if not path or not os.path.exists(path):
        print("ERROR: no brief JSON found", file=sys.stderr)
        return 1

    with open(path) as f:
        brief = json.load(f)

    text = format_message(brief, env.get("SITE_URL", ""))
    parts = split_message(text)
    for i, part in enumerate(parts, 1):
        res = send(token, chat_id, part)
        if not res.get("ok"):
            print(f"ERROR: telegram send failed (part {i}/{len(parts)}): {res}", file=sys.stderr)
            return 1
        if i < len(parts):
            time.sleep(1)
    print(f"OK: sent brief {brief.get('date')} to chat {chat_id} ({len(parts)} message(s))")
    return 0


if __name__ == "__main__":
    sys.exit(main())
