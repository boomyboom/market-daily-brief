#!/usr/bin/env python3
"""Deterministic pre-publication checks for market brief JSON files."""

import json
import os
import re
import sys
from urllib.parse import urlparse


KR_SECTORS = [
    "반도체", "IT/기술", "통신", "바이오/제약", "금융", "유통/소비재",
    "자동차", "2차전지", "조선/방산", "건설", "화학/소재", "철강/금속",
    "인터넷/게임", "엔터/미디어",
]
US_SECTORS = [
    "반도체", "기술(빅테크)", "통신서비스", "헬스케어", "금융", "경기소비재",
    "필수소비재", "산업재", "소재", "에너지", "유틸리티", "부동산",
]
ASSETS = ["원/달러", "달러인덱스", "금", "WTI", "비트코인", "이더리움", "미 10년물"]
PCT_RE = re.compile(r"^(?:[+-]\d+(?:\.\d+)?|0(?:\.0+)?)%(?:\(|$)")
NUM_RE = re.compile(r"^[^0-9+-]*([+-]?\d+(?:\.\d+)?)")
BAD_PUNCT = ("·", "・", "—", "–")
DENIED_HOSTS = {
    "reddit.com", "www.reddit.com", "x.com", "twitter.com", "www.twitter.com",
    "facebook.com", "www.facebook.com", "instagram.com", "www.instagram.com",
    "threads.net", "www.threads.net", "threads.com", "www.threads.com",
    "youtube.com", "www.youtube.com", "youtu.be", "blog.naver.com",
}


def pct_value(value):
    match = NUM_RE.search(str(value or "").strip())
    return float(match.group(1)) if match else None


def urls_for(item):
    urls = []
    if item.get("source_url"):
        urls.append(item["source_url"])
    many = item.get("source_urls") or item.get("sources") or []
    if isinstance(many, str):
        many = [many]
    urls.extend(value for value in many if value)
    return list(dict.fromkeys(urls))


def walk_strings(node, path=""):
    if isinstance(node, str):
        yield path, node
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from walk_strings(value, f"{path}[{index}]")
    elif isinstance(node, dict):
        for key, value in node.items():
            yield from walk_strings(value, f"{path}.{key}" if path else key)


def validate_url(url, label, errors):
    try:
        parsed = urlparse(url)
    except Exception:
        parsed = None
    if not parsed or parsed.scheme not in ("http", "https") or not parsed.netloc:
        errors.append(f"{label}: 올바르지 않은 출처 URL")
        return
    host = parsed.netloc.lower().split(":", 1)[0]
    if host in DENIED_HOSTS or host.endswith(".reddit.com"):
        errors.append(f"{label}: 허용되지 않은 출처 {host}")


def require_sources(item, label, errors, minimum=1):
    urls = urls_for(item)
    if len(urls) < minimum:
        errors.append(f"{label}: 출처 {minimum}개 이상 필요")
    for url in urls:
        validate_url(url, label, errors)


def validate_sector_group(items, expected, label, errors):
    names = [str(item.get("name") or "") for item in items]
    if names != expected:
        errors.append(f"{label}: 섹터 이름 또는 순서 불일치")
    for index, item in enumerate(items):
        name = item.get("name") or f"{index + 1}번"
        pct = str(item.get("change_pct") or "").strip()
        if "미확인" in pct or not PCT_RE.match(pct):
            errors.append(f"{label} {name}: 정확한 부호와 등락률 필요")
        require_sources(item, f"{label} {name}", errors)


def validate(path):
    errors = []
    try:
        with open(path, encoding="utf-8") as file:
            brief = json.load(file)
    except Exception as exc:
        return [f"JSON 읽기 실패: {exc}"]

    if brief.get("date") != os.path.basename(path)[:10]:
        errors.append("date가 파일명 날짜와 다름")
    if not str(brief.get("headline") or "").strip():
        errors.append("headline 누락")
    if not str(brief.get("mail_title") or "").strip():
        errors.append("mail_title 누락")
    if "투자 권유" not in str(brief.get("disclaimer") or ""):
        errors.append("면책 고지 누락")

    for text_path, value in walk_strings(brief):
        if text_path.endswith("url") or "source_urls[" in text_path or "sources[" in text_path:
            continue
        if any(mark in value for mark in BAD_PUNCT):
            errors.append(f"{text_path}: 금지 문장부호 포함")

    session = brief.get("session")
    is_kr_close_file = os.path.basename(path).endswith("-kr.json")
    if is_kr_close_file and session != "kr_close":
        errors.append("한국장 마감 파일은 session이 kr_close여야 함")
    if not is_kr_close_file and session == "kr_close":
        errors.append("아침 브리핑 파일에 kr_close session을 사용할 수 없음")
    sectors = brief.get("sectors") or {}
    validate_sector_group(sectors.get("kr") or [], KR_SECTORS, "한국 섹터", errors)
    if not is_kr_close_file:
        validate_sector_group(sectors.get("us") or [], US_SECTORS, "미국 섹터", errors)

    for market, items in (
        ("한국 지수", (brief.get("kr") or {}).get("indices") or []),
        ("미국 지수", (brief.get("us") or {}).get("indices") or []),
    ):
        for item in items:
            move = abs(pct_value(item.get("change_pct")) or 0)
            require_sources(item, f"{market} {item.get('name')}", errors, 2 if move >= 5 else 1)

    for group, items in (
        ("한국 종목", (brief.get("kr") or {}).get("hot_stocks") or []),
        ("미국 종목", (brief.get("us") or {}).get("notable") or []),
    ):
        for item in items:
            move = abs(pct_value(item.get("change_pct")) or 0)
            require_sources(item, f"{group} {item.get('name') or item.get('ticker')}", errors,
                            2 if move >= 15 else 1)

    assets = brief.get("assets") or []
    if [str(item.get("name") or "") for item in assets] != ASSETS:
        errors.append("핵심 지표 이름 또는 순서 불일치")
    for item in assets:
        if "미확인" in str(item.get("value") or "") or not item.get("value"):
            errors.append(f"핵심 지표 {item.get('name')}: 값 누락")
        require_sources(item, f"핵심 지표 {item.get('name')}", errors)

    for item in (brief.get("top_themes") or []) + (brief.get("watchlist") or []):
        label = item.get("theme") or item.get("name") or item.get("ticker")
        require_sources(item, f"출처 항목 {label}", errors)
    for item in brief.get("spotlight") or []:
        require_sources(item, f"주목 종목 {item.get('name') or item.get('ticker')}", errors)
    return errors


def main():
    if len(sys.argv) != 2:
        print("usage: validate_brief.py <brief.json>", file=sys.stderr)
        return 2
    errors = validate(sys.argv[1])
    if errors:
        print(f"FAIL: {len(errors)}개 검증 오류", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print(f"OK: validated {sys.argv[1]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
