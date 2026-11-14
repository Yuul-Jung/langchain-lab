"""답변에 출처 표시를 코드로 붙인다 (모델 호출 없음).

모델이 [자료 N] 을 빼먹는 경우(평가에서 답의 절반)를 위해, 답과 가장 글이 겹치는 근거를 찾아 '근거:' 줄로 붙인다.
- 모델이 이미 유효한 [자료 N] 을 썼으면 그대로 둔다. 없는 번호(근거 개수 초과)는 지운다.
- 겹침 = 답의 글자 4-gram 중 그 근거에도 있는 비율. 가장 높은 근거와 그 절반 이상인 근거를 최대 2개.
- 이 값들(N=4, 절반, 최대 2개)은 결과를 보기 전에 정했고, 평가 결과에 맞춰 조정하지 않는다.
- 겹치는 근거가 하나도 없으면 아무것도 붙이지 않는다 (근거 없는 출처를 지어내지 않는다).
"""
from __future__ import annotations

import re

import chat_search

NGRAM = 4
RELATIVE_MIN = 0.5
MAX_CITED = 2
_MARK = re.compile(r"\[자료\s*(\d+)\]")
_KEEP = re.compile(r"[0-9a-z가-힣]+")


def _grams(text: str) -> set[str]:
    flat = "".join(_KEEP.findall(_MARK.sub(" ", text.lower())))
    return {flat[i:i + NGRAM] for i in range(len(flat) - NGRAM + 1)}


def attribute(answer: str, sources: list[dict]) -> list[tuple[int, float]]:
    """(근거 번호 1부터, 겹침 비율) 목록, 겹침 큰 순. 겹침이 없으면 빈 목록."""
    grams = _grams(answer)
    if not grams:
        return []
    shares = [(i, len(grams & _grams(s.get("text", ""))) / len(grams)) for i, s in enumerate(sources, 1)]
    shares = [x for x in shares if x[1] > 0]
    if not shares:
        return []
    best = max(share for _, share in shares)
    chosen = [x for x in shares if x[1] >= best * RELATIVE_MIN]
    chosen.sort(key=lambda x: (-x[1], x[0]))
    return chosen[:MAX_CITED]


def add_citations(answer: str, sources: list[dict]) -> tuple[str, dict]:
    """(출처 처리한 답, 처리 내용 {'removed_bad': n, 'added': [번호...], 'kept': bool})."""
    info = {"removed_bad": 0, "added": [], "kept": False}
    if not sources:
        return answer, info
    n = len(sources)

    def drop_bad(m):
        if 1 <= int(m.group(1)) <= n:
            return m.group(0)
        info["removed_bad"] += 1
        return ""

    answer = _MARK.sub(drop_bad, answer)
    if _MARK.search(answer):
        info["kept"] = True
        return answer, info
    picked = attribute(answer, sources)
    if not picked:
        return answer, info
    info["added"] = [i for i, _ in picked]
    line = ", ".join(f"[자료 {i}] ({chat_search.label(sources[i - 1])})" for i, _ in picked)
    return answer.rstrip() + f"\n\n근거: {line}", info
