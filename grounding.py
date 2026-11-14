"""답에 나온 숫자·영문 용어가 근거 자료(와 질문)에 실제로 있는지 대조한다 — 모델 호출 없음.

'근거에서 못 찾았다'는 것이 곧 '지어냈다'는 뜻은 아니다: 답이 계산한 값(합계 등), 일반 상식의 낱말,
표기 차이(이중 기호·단위 붙여 쓰기)도 걸릴 수 있다. 이 도구는 사람이 확인할 후보를 좁혀 주는 용도이고,
답이 옳은지 판정하지 않는다. 반대로 근거에 있는 숫자를 엉뚱한 곳에 쓴 틀린 답은 걸러내지 못한다.

대조 대상
  - 숫자: 12,340 · 3.5 · 27 같은 것 (쉼표는 무시). 목록 번호(줄 머리의 '1.')와 [자료 N] 표시는 뺀다.
  - 영문 용어: 알파벳으로 시작하는 3자 이상 낱말 (대소문자 무시). 답의 형식 표시(예: 'http')는 따로 빼지 않는다.
질문에 이미 있는 값은 사용자가 준 것이므로 근거로 인정한다.
"""
from __future__ import annotations

import re

_CITATION = re.compile(r"\[자료\s*\d+\]")
_LIST_NUMBER = re.compile(r"(?m)^\s*\d+[.)]\s")
_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")
_WORD = re.compile(r"[A-Za-z][A-Za-z0-9_\-]{2,}")


def _numbers(text: str) -> list[str]:
    text = _LIST_NUMBER.sub(" ", _CITATION.sub(" ", text))
    return list(dict.fromkeys(n.rstrip(",").replace(",", "") for n in _NUMBER.findall(text)))


def _words(text: str) -> list[str]:
    return list(dict.fromkeys(w.lower() for w in _WORD.findall(_CITATION.sub(" ", text))))


def _has_number(number: str, haystack: str) -> bool:
    """자릿수가 이어지지 않는 위치에서 찾는다 ('8' 이 '18' 안에서 찾아지면 안 된다)."""
    return re.search(r"(?<!\d)(?<!\d\.)" + re.escape(number) + r"(?![\d]|\.\d)", haystack) is not None


def source_texts(sources: list[dict]) -> list[str]:
    """채팅이 모델에게 준 자료의 글: 본문과 함께 머리말(파일 이름·제목·쪽)도 모델이 본 것이므로 근거로 인정한다."""
    out = []
    for s in sources:
        out.append(str(s.get("text") or ""))
        out.append(" ".join(str(s.get(k) or "") for k in ("filename", "title")) + (f" p.{s['page']}" if s.get("page") else ""))
    return out


def check(answer: str, sources: list[str], question: str = "") -> dict:
    """{'numbers': 근거에서 못 찾은 숫자, 'words': 못 찾은 영문 용어, 'checked': 대조한 개수}"""
    evidence = "\n".join(sources) + "\n" + question
    flat_numbers = evidence.replace(",", "")
    lowered = evidence.lower()
    nums, words = _numbers(answer), _words(answer)
    return {
        "numbers": [n for n in nums if not _has_number(n, flat_numbers)],
        "words": [w for w in words if w not in lowered],
        "checked": len(nums) + len(words),
    }
