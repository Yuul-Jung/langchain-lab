"""한·영 다리 사전 사용 (5단계): 질문 속 한국어 구절과 맞는 영어 구절을 찾아 낱말 검색에 덧붙인다.

사전: data/ontology/bridge_phrases.jsonl (scripts/mine-bridge-phrases.py → propose-bridge-ko.py 로 만듦).
승인 기록: data/ontology/bridge_approvals.jsonl ({'en', 'ko', 'decision', 'approver', ...}, 마지막 줄이 이김).
- 승인된(approved) 항목만 쓴다. 사전·승인 파일이 없으면 아무것도 덧붙이지 않는다.
- 한국어 구절은 띄어쓰기를 무시하고 맞춘다('공급 전압' = '공급전압'). 긴 구절이 먼저(겹치면 긴 것만).
- 한 글자 한국어는 쓰지 않는다(오탐). 한글이 없는 항목(영어 그대로)도 쓰지 않는다 — 질문에 이미 영어가 있으면 낱말 검색이 찾는다.
- 쓰는 곳(설정, 기본 꺼짐): DOCUMENT_BRIDGE(문서 낱말 검색), PARTS_BRIDGE(부품 검색어 덧붙임).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PHRASES = ROOT / "data" / "ontology" / "bridge_phrases.jsonl"
APPROVALS = ROOT / "data" / "ontology" / "bridge_approvals.jsonl"
MAX_TERMS = 6
_cache: dict = {}


def _read(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def load(phrases: Path = PHRASES, approvals: Path = APPROVALS) -> list[tuple[str, str]]:
    """[(띄어쓰기 없앤 한국어, 영어)] — 승인된 것만, 긴 한국어 먼저. 파일이 바뀌면 다시 읽는다."""
    key = tuple((p, p.stat().st_mtime if p.is_file() else None) for p in (phrases, approvals))
    if _cache.get("key") == key:
        return _cache["rows"]
    decision = {}
    for r in _read(approvals):
        if "decision" in r and r.get("en"):
            decision[(r["en"], r.get("ko", ""))] = r["decision"]
    rows = []
    for r in _read(phrases):
        ko, en = (r.get("ko") or "").strip(), (r.get("en") or "").strip()
        flat = re.sub(r"\s+", "", ko)
        if decision.get((en, ko)) == "approved" and re.search(r"[가-힣]", flat) and len(flat) >= 2:
            rows.append((flat, en))
    rows.sort(key=lambda t: -len(t[0]))
    _cache.update(key=key, rows=rows)
    return rows


def english_for(question: str, rows: list[tuple[str, str]] | None = None) -> list[str]:
    """질문에 든 한국어 구절의 영어 짝(질문에 이미 있는 영어는 빼고, 최대 MAX_TERMS 개)."""
    rows = load() if rows is None else rows
    flat = re.sub(r"\s+", "", question)
    lowered = question.lower()
    taken: list[tuple[int, int]] = []
    out: list[str] = []
    for ko, en in rows:
        start = flat.find(ko)
        while start != -1:
            span = (start, start + len(ko))
            if not any(a < span[1] and span[0] < b for a, b in taken):
                taken.append(span)
                if en.lower() not in lowered and en not in out:
                    out.append(en)
                break
            start = flat.find(ko, start + 1)
        if len(out) >= MAX_TERMS:
            break
    return out
