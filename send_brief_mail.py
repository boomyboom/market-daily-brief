#!/usr/bin/env python3
"""Email a market brief in the dashboard's layout.

The owner likes how boomyboom.github.io/market-daily-brief renders, so this
rebuilds that layout as self-contained HTML and mails it. Mail.app's
`html content` is broken on this machine, so the HTML source is sent as plain
text and the reader can paste it anywhere; the dashboard link is included for
the rendered view.

Usage:
    python3 send_brief_mail.py                       # latest morning brief
    python3 send_brief_mail.py briefs/2026-07-28-kr.json
"""
import glob
import html as H
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
BRIEFS = os.path.join(ROOT, "briefs")


def load_env():
    env = {}
    p = os.path.join(ROOT, ".env")
    if os.path.exists(p):
        for line in open(p):
            s = line.strip()
            if s and not s.startswith("#") and "=" in s:
                k, v = s.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def esc(s):
    return H.escape(str(s or ""))


def pct_num(s):
    m = "".join(c for c in str(s or "") if c in "0123456789.-")
    try:
        return float(m)
    except ValueError:
        return None


def heat(p):
    """Same colour rule the dashboard uses."""
    n = pct_num(p)
    if n is None:
        return "#f2f2f2", "#666"
    a = min(abs(n) / 3.0, 1.0) * 0.75 + 0.08
    return (f"rgba(63,179,127,{a:.2f})" if n >= 0 else f"rgba(229,83,75,{a:.2f})"), "#111"


def colour(p):
    n = pct_num(p)
    if n is None:
        return "#666"
    return "#137a4f" if n > 0 else ("#c0392b" if n < 0 else "#666")


def tiles(arr, label):
    if not arr:
        return ""
    out = [f'<h3 style="font-size:14px;color:#666;margin:18px 0 8px">{label}</h3>',
           '<table role="presentation" cellpadding="0" cellspacing="6"><tr>']
    for i in arr:
        if not i.get("name"):
            continue
        out.append(
            '<td style="border:1px solid #e2e8f0;border-radius:8px;padding:8px 12px">'
            f'<div style="font-size:12px;color:#666">{esc(i.get("name"))}</div>'
            f'<div style="font-size:16px;font-weight:600">{esc(i.get("value"))} '
            f'<span style="color:{colour(i.get("change_pct"))}">{esc(i.get("change_pct"))}</span></div></td>')
    out.append("</tr></table>")
    return "".join(out)


def heatmap(sectors, label):
    if not sectors:
        return ""
    cells = []
    for s in sectors:
        bg, fg = heat(s.get("change_pct"))
        cells.append(
            f'<td style="background:{bg};color:{fg};border:1px solid #e2e8f0;border-radius:8px;'
            'padding:8px 6px;text-align:center;font-size:12px;min-width:84px">'
            f'<div style="font-weight:600">{esc(s.get("name"))}</div>'
            f'<div style="font-weight:700;margin-top:2px">{esc(s.get("change_pct"))}</div></td>')
    rows = ["".join(cells[i:i + 6]) for i in range(0, len(cells), 6)]
    body = "".join(f"<tr>{r}</tr>" for r in rows)
    return (f'<h3 style="font-size:14px;color:#666;margin:18px 0 8px">{label}</h3>'
            f'<table role="presentation" cellpadding="0" cellspacing="5">{body}</table>')


def items(arr, title, name_key="name", pct_key="change_pct", why_key="reason"):
    if not arr:
        return ""
    out = [f'<h3 style="font-size:15px;margin:20px 0 6px">{title}</h3>']
    for x in arr:
        nm = esc(x.get(name_key) or x.get("ticker"))
        pct = esc(x.get(pct_key))
        why = esc(x.get(why_key) or x.get("thesis") or x.get("summary"))
        out.append(
            '<div style="padding:8px 0;border-top:1px solid #eee">'
            f'<div style="font-weight:600">{nm} '
            f'<span style="color:{colour(x.get(pct_key))}">{pct}</span></div>'
            f'<div style="font-size:13px;color:#555;margin-top:2px">{why}</div></div>')
    return "".join(out)


def build_html(b, site_url):
    kr = b.get("kr", {}) or {}
    us = b.get("us", {}) or {}
    sec = b.get("sectors", {}) or {}
    is_kr = b.get("session") == "kr_close"
    head = "한국장 마감 브리핑" if is_kr else "오늘의 시장 브리핑"

    P = ['<div style="font-family:-apple-system,BlinkMacSystemFont,\'Apple SD Gothic Neo\',sans-serif;'
         'max-width:680px;color:#1a2230;line-height:1.6">']
    P.append(f'<h1 style="font-size:20px;margin:0 0 4px">{head} {esc(b.get("date",""))}</h1>')
    if b.get("headline"):
        P.append(f'<p style="background:#f7f8fa;border-left:3px solid #2b6cb0;padding:10px 12px;'
                 f'margin:10px 0 18px;font-weight:600">{esc(b["headline"])}</p>')
    if site_url:
        P.append(f'<p style="font-size:13px"><a href="{esc(site_url)}">대시보드에서 보기</a></p>')

    if kr.get("indices") or kr.get("hot_stocks"):
        P.append('<h2 style="font-size:17px;margin:24px 0 4px">한국장</h2>')
        P.append(tiles(kr.get("indices"), "지수"))
        if kr.get("preview"):
            P.append(f'<p style="font-size:14px;color:#444">{esc(kr["preview"])}</p>')
        P.append(items(kr.get("hot_stocks"), "오늘의 화제 종목"))

    if sec.get("kr") or sec.get("us"):
        P.append('<h2 style="font-size:17px;margin:24px 0 4px">섹터 히트맵</h2>')
        P.append(heatmap(sec.get("kr"), "한국"))
        P.append(heatmap(sec.get("us"), "미국"))

    if us.get("recap") or us.get("indices"):
        P.append('<h2 style="font-size:17px;margin:24px 0 4px">미국장</h2>')
        P.append(tiles(us.get("indices"), "지수"))
        if us.get("recap"):
            P.append(f'<p style="font-size:14px;color:#444">{esc(us["recap"])}</p>')
        P.append(items(us.get("notable"), "주요 종목"))

    if b.get("assets"):
        P.append('<h2 style="font-size:17px;margin:24px 0 4px">환율, 금, 코인</h2>')
        P.append(tiles(b["assets"], ""))

    m = b.get("macro", {}) or {}
    if m.get("rates_fx_commodities") or m.get("notes"):
        P.append('<h2 style="font-size:17px;margin:24px 0 4px">매크로</h2>')
        for v in (m.get("rates_fx_commodities"), m.get("notes")):
            if v:
                P.append(f'<p style="font-size:14px;color:#444">{esc(v)}</p>')

    if b.get("top_themes"):
        P.append('<h2 style="font-size:17px;margin:24px 0 4px">오늘의 테마</h2>')
        P.append(items(b["top_themes"], "", name_key="theme", pct_key="_", why_key="summary"))

    P.append('<p style="font-size:12px;color:#888;margin-top:24px;border-top:1px solid #eee;'
             'padding-top:10px">정보 제공용이며 투자 권유가 아닙니다.</p></div>')
    return "".join(P)


def applescript_escape(s):
    return s.replace("\\", "\\\\").replace('"', '\\"')


def send(to_addr, subject, text):
    import tempfile
    fd, tmp = tempfile.mkstemp(suffix=".txt")
    with os.fdopen(fd, "w") as f:
        f.write(text)
    try:
        script = f'''
        set bodyText to (read POSIX file "{applescript_escape(tmp)}" as «class utf8»)
        tell application "Mail"
            set m to make new outgoing message with properties {{subject:"{applescript_escape(subject)}", content:bodyText, visible:false}}
            tell m
                make new to recipient at end of to recipients with properties {{address:"{applescript_escape(to_addr)}"}}
            end tell
            send m
        end tell
        '''
        r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=90)
        if r.returncode != 0:
            raise RuntimeError(r.stderr.strip() or "osascript failed")
    finally:
        os.unlink(tmp)


def main():
    env = load_env()
    to_addr = env.get("MAIL_TO")
    if not to_addr:
        print("ERROR: MAIL_TO not set in .env", file=sys.stderr)
        return 1

    if len(sys.argv) > 1:
        path = sys.argv[1]
    else:
        cands = [f for f in sorted(glob.glob(os.path.join(BRIEFS, "20*-*-*.json")))
                 if not f.endswith("-kr.json")]
        path = cands[-1] if cands else None
    if not path or not os.path.exists(path):
        print("no brief found", file=sys.stderr)
        return 1

    b = json.load(open(path))
    site = env.get("SITE_URL", "")
    body = build_html(b, site)

    is_kr = b.get("session") == "kr_close"
    label = "한국장 마감" if is_kr else "시장 브리핑"
    guide = (f"[{label}] {b.get('date','')}\n"
             f"대시보드: {site}\n\n"
             f"아래 HTML을 그대로 붙여넣으면 대시보드와 같은 형태로 보입니다.\n"
             f"=====================================\n")
    send(to_addr, f"[{label}] {b.get('date','')} {(b.get('headline') or '')[:40]}",
         guide + body + "\n=====================================\n")
    print(f"OK: brief mail sent to {to_addr} ({os.path.basename(path)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
