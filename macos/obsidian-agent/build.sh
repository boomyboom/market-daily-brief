#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
APP="/Applications/BoomyBoom Obsidian Agent.app"
BUILD="$(mktemp -d)"
trap 'rm -rf "$BUILD"' EXIT

mkdir -p "$BUILD/BoomyBoom Obsidian Agent.app/Contents/MacOS"
cp "$ROOT/Info.plist" "$BUILD/BoomyBoom Obsidian Agent.app/Contents/Info.plist"
/usr/bin/clang -Wall -Wextra -O2 "$ROOT/main.c" \
  -o "$BUILD/BoomyBoom Obsidian Agent.app/Contents/MacOS/boomyboom-obsidian-agent"
/usr/bin/codesign --force --deep --sign - "$BUILD/BoomyBoom Obsidian Agent.app"
/usr/bin/ditto "$BUILD/BoomyBoom Obsidian Agent.app" "$APP"
/usr/bin/codesign --verify --deep --strict "$APP"
echo "Installed: $APP"
