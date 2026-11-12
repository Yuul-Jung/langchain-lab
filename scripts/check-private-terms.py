#!/usr/bin/env python3
"""올리기 전 확인: 내 문서에서 나온 낱말·숫자가 올릴 파일에 섞였는지 대조한다 (읽기 전용).

평가 자료(data/eval/ — GitHub에 올라가지 않음)의 정답 낱말(answer_keys)·핵심어(keywords)·
한 단어 검색어(keywords.txt)를 "내 문서에서 나온 낱말"로 보고, 바뀐 파일에 그 낱말이 있는지 찾는다.
테스트·교재의 예시는 지어낸 값이어야 한다. 겹치는 낱말이 있으면 지어낸 값으로 바꾼다.

  - 띄어쓰기와 대소문자는 무시한다. 3자 미만의 낱말은 대조하지 않는다.
  - 흔한 낱말(Python 등)이 걸리면 data/eval/allow-terms.txt 에 한 줄씩 적어 제외한다.
  - 이 도구가 아는 것은 평가 자료에 적힌 낱말뿐이다. 통과했다고 문서 내용이 전혀 없다는 뜻은 아니다.

사용:
  .venv/bin/python scripts/check-private-terms.py            # 마지막 커밋 뒤에 바뀐 파일
  .venv/bin/python scripts/check-private-terms.py --all      # 저장소의 모든 글 파일
  .venv/bin/python scripts/check-private-terms.py 파일 ...   # 지정한 파일
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EVAL_DIR = ROOT / "data" / "eval"
MIN_CHARS = 3
TEXT_SUFFIXES = {".py", ".md", ".html", ".json", ".txt", ".sh", ".yml", ".yaml", ".css", ".js", ".svg", ".example"}


def norm(text) -> str:
    """띄어쓰기와 대소문자를 무시하고 비교하기 위한 꼴."""
    return "".join(str(text).split()).lower()


def collect_terms(eval_dir) -> set[str]:
    """평가 자료에서 내 문서의 낱말을 모은다 (허용 목록에 적은 것은 뺀다)."""
    eval_dir = Path(eval_dir)
    terms: set[str] = set()
    for path in sorted(eval_dir.glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            try:
                item = json.loads(line)
            except ValueError:
                continue
            for group in item.get("answer_keys") or []:
                terms.update(str(alt) for alt in group)
            terms.update(str(word) for word in item.get("keywords") or [])
    for name in ("keywords.txt",):
        path = eval_dir / name
        if path.exists():
            terms.update(line.strip() for line in path.read_text(encoding="utf-8").splitlines()
                         if line.strip() and not line.startswith("#"))
    allow = eval_dir / "allow-terms.txt"
    allowed = {norm(line) for line in allow.read_text(encoding="utf-8").splitlines()
               if line.strip() and not line.startswith("#")} if allow.exists() else set()
    return {term for term in terms if len(norm(term)) >= MIN_CHARS and norm(term) not in allowed}


_EMBEDDED = re.compile(r"data:[a-z0-9/+.-]+;base64,[A-Za-z0-9+/=]+")     # 파일 안에 넣은 그림 (아무 글자열이나 나올 수 있다)
_ASCII_WORD = re.compile(r"[A-Za-z0-9]+")


def find_terms(text: str, terms) -> list[str]:
    """글에 들어 있는 낱말들 (띄어쓰기·대소문자 무시).

    영문·숫자만으로 된 낱말은 앞뒤가 영문·숫자가 아닐 때만 센다('LOG' 가 'BLOG' 에 걸리지 않게).
    """
    text = _EMBEDDED.sub(" ", text)
    flat = norm(text)
    found = []
    for term in terms:
        parts = str(term).split()
        if parts and all(_ASCII_WORD.fullmatch(part) for part in parts):
            pattern = r"(?<![A-Za-z0-9])" + r"\s*".join(re.escape(part) for part in parts) + r"(?![A-Za-z0-9])"
            if re.search(pattern, text, re.IGNORECASE):
                found.append(term)
        elif norm(term) in flat:
            found.append(term)
    return sorted(found)


def changed_files() -> list[str]:
    """마지막 커밋 뒤에 바뀌었거나 새로 생긴 파일 (GitHub에 올라가지 않는 파일 제외)."""
    out = subprocess.run(["git", "status", "--porcelain", "-z", "--untracked-files=all"], cwd=ROOT,
                         capture_output=True, text=True, check=True).stdout
    return parse_status(out)


def parse_status(out: str) -> list[str]:
    """`git status --porcelain -z` 출력에서 지금 있는 파일 이름만 뽑는다 (지운 파일·이름 바꾸기 전 이름 제외)."""
    names, entries, i = [], out.split("\0"), 0
    while i < len(entries):
        entry = entries[i]
        i += 1
        if len(entry) < 4:
            continue
        state, name = entry[:2], entry[3:]
        if state[0] in "RC":
            i += 1                      # 이름을 바꾼 경우 다음 항목은 예전 이름
        if "D" not in state:
            names.append(name)
    return names


def all_files() -> list[str]:
    out = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    return [name for name in out.split("\0") if name]


def main():
    parser = argparse.ArgumentParser(description="내 문서의 낱말이 올릴 파일에 섞였는지 대조 (읽기 전용)")
    parser.add_argument("files", nargs="*")
    parser.add_argument("--all", action="store_true", help="저장소의 모든 글 파일을 본다")
    parser.add_argument("--eval-dir", default=str(EVAL_DIR))
    args = parser.parse_args()

    if not Path(args.eval_dir).is_dir():
        print("대조할 평가 자료가 없습니다:", args.eval_dir)
        return 0
    terms = collect_terms(args.eval_dir)
    names = args.files or (all_files() if args.all else changed_files())
    found = 0
    checked = 0
    for name in names:
        path = (ROOT / name) if not Path(name).is_absolute() else Path(name)
        if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        checked += 1
        hits = find_terms(text, terms)
        if hits:
            found += 1
            print(f"{name}: 겹치는 낱말 {len(hits)}개 → {', '.join(hits[:12])}{' …' if len(hits) > 12 else ''}")
    print(f"대조한 낱말 {len(terms)}개 · 본 파일 {checked}개 · 겹치는 파일 {found}개")
    if found:
        print("겹치는 낱말이 문서에서 온 것이면 지어낸 값으로 바꾸세요. 흔한 낱말이면 data/eval/allow-terms.txt 에 적어 제외합니다.")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
