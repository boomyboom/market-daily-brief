#!/usr/bin/env python3
"""Archive legacy combined market notes before session-aware backfill.

Older exports used one daily note name for both the morning and Korean close
briefs. This migration preserves those files in an archive and removes their
now-stale entity timeline links. Running it more than once is safe.
"""

import os
import re
import shutil

from brief_to_obsidian import load_env_vault


LEGACY_NAME = re.compile(r"^(20\d{2}-\d{2}-\d{2}) 시장\.md$")
LEGACY_LINK = re.compile(
    r"^- (20\d{2}-\d{2}-\d{2}) \[\[\1 시장\]\].*\n?", re.MULTILINE
)


def main():
    vault = load_env_vault()
    daily_dir = os.path.join(vault, "10_주식뇌", "_데일리")
    archive_dir = os.path.join(vault, "90_Archive", "legacy-market-daily")
    os.makedirs(archive_dir, exist_ok=True)

    moved = 0
    for name in os.listdir(daily_dir):
        if not LEGACY_NAME.match(name):
            continue
        source = os.path.join(daily_dir, name)
        target = os.path.join(archive_dir, name)
        if not os.path.exists(target):
            shutil.move(source, target)
            moved += 1

    cleaned = 0
    entity_root = os.path.join(vault, "10_주식뇌")
    for root, _, files in os.walk(entity_root):
        if os.path.abspath(root) == os.path.abspath(daily_dir):
            continue
        for name in files:
            if not name.endswith(".md"):
                continue
            path = os.path.join(root, name)
            with open(path, encoding="utf-8") as file:
                old = file.read()
            new = LEGACY_LINK.sub("", old)
            if new != old:
                with open(path, "w", encoding="utf-8") as file:
                    file.write(new)
                cleaned += 1

    print(f"OK: archived {moved} legacy daily notes, cleaned {cleaned} entity notes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
