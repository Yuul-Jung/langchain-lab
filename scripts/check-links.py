#!/usr/bin/env python3
"""공개 사이트(GitHub Pages)의 내부 링크 검사 — 읽기 전용.

검사 대상: 시작 페이지 index.html, 예전 주소 이동 페이지 docs/*.html,
교재 education/dist/*.html(좌측 메뉴용 장 목록 포함), README.md
건너뜀: 외부 주소(http·https), 내 PC 주소(127.0.0.1), langchainlab:// 실행 버튼, 같은 페이지 #앵커

교재 장별 파일명은 버전(_vNN)이 바뀌므로, 버전을 올린 뒤 시작 페이지·이동 페이지 링크를
고치지 않으면 여기서 실패한다. 서비스 실행과는 무관하므로 update-local.sh 에서는 돌리지 않는다.
사용: python scripts/check-links.py   (끊긴 링크가 있으면 종료 코드 1)
"""
import json
import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parent.parent
SKIP = ("http://", "https://", "mailto:", "langchainlab:", "javascript:", "data:", "#")


def pages():
    yield ROOT / "index.html"
    yield from sorted((ROOT / "docs").glob("*.html"))
    yield from sorted((ROOT / "education" / "dist").glob("*.html"))


def links(path):
    text = path.read_text(encoding="utf-8")
    found = re.findall(r'(?:href|src)="([^"]+)"', text)
    found += re.findall(r"location\.replace\('([^']+)'\)", text)
    found += re.findall(r'content="0; url=([^"]+)"', text)
    m = re.search(r"window\.COURSE=(\{.*?\});</script>", text)
    if m:  # 좌측 메뉴·이전/다음 버튼이 쓰는 장 목록
        found += [ch["file"] for ch in json.loads(m.group(1))["chapters"]]
    return found


def readme_links():
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    return re.findall(r"\]\(([^)\s]+)\)", text)


def broken(base, targets):
    bad = []
    for raw in targets:
        if raw.startswith(SKIP) or "127.0.0.1" in raw:
            continue
        rel = unquote(urlsplit(raw).path)
        if not rel:
            continue
        target = (base / rel).resolve()
        if ROOT not in target.parents and target != ROOT:
            bad.append((raw, "저장소 밖을 가리킴"))
        elif not target.exists():
            bad.append((raw, "파일 없음"))
    return bad


def main():
    problems, checked = [], 0
    for page in pages():
        targets = links(page)
        checked += len(targets)
        problems += [(page, *b) for b in broken(page.parent, targets)]
    targets = readme_links()
    checked += len(targets)
    problems += [(ROOT / "README.md", *b) for b in broken(ROOT, targets)]
    for page, raw, why in problems:
        print(f"끊긴 링크: {page.relative_to(ROOT)} → {raw} ({why})")
    print(f"검사한 링크 {checked}개, 끊긴 링크 {len(problems)}개")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
