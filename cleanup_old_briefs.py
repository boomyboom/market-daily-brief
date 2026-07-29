#!/usr/bin/env python3
"""Remove briefs older than RETENTION_DAYS and regenerate manifest.json.

A day can hold two sessions: the morning brief (`YYYY-MM-DD.json`, US-led) and
the Korean close brief (`YYYY-MM-DD-kr.json`, 19:00). Both are listed as
separate entries so neither overwrites the other, newest first, with the
evening session ahead of the morning one on the same date.
"""
import json
import os
import glob
import re
from datetime import datetime, date

ROOT = os.path.dirname(os.path.abspath(__file__))
BRIEFS_DIR = os.path.join(ROOT, "briefs")
RETENTION_DAYS = 30
FILE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})(-kr)?\.json$")

# 같은 날짜 안에서의 순서 (숫자가 클수록 위로)
SESSION_RANK = {"kr_close": 2, "morning": 1}
SESSION_LABEL = {"kr_close": "한국장 마감", "morning": "미국장, 아침"}


def main():
    os.makedirs(BRIEFS_DIR, exist_ok=True)
    today = date.today()
    entries = []

    for path in sorted(glob.glob(os.path.join(BRIEFS_DIR, "20*-*-*.json"))):
        name = os.path.basename(path)
        m = FILE_RE.match(name)
        if not m:
            continue
        d = datetime.strptime(m.group(1), "%Y-%m-%d").date()
        if (today - d).days > RETENTION_DAYS:
            os.remove(path)
            print(f"removed old brief: {name}")
            continue
        session = "kr_close" if m.group(2) else "morning"
        entries.append({
            "key": name[:-5],                     # 확장자 제외, index.html 이 그대로 로드
            "date": m.group(1),
            "session": session,
            "label": f"{m.group(1)} {SESSION_LABEL[session]}",
        })

    entries.sort(key=lambda e: (e["date"], SESSION_RANK[e["session"]]), reverse=True)

    manifest = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "latest": entries[0]["key"] if entries else None,
        "dates": [e["key"] for e in entries],     # 이전 형식 호환
        "entries": entries,
    }
    with open(os.path.join(BRIEFS_DIR, "manifest.json"), "w") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    print(f"manifest updated: {len(entries)} briefs, latest={manifest['latest']}")


if __name__ == "__main__":
    main()
