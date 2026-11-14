"""한국어 문장 속에 섞인 한자를 한글 음으로 바꾼다 (모델 호출 없음).

표(static_data/hanja_ko.json)는 유니코드 Unihan 의 한글 음에서 만들었고(scripts/build-hanja-table.py),
음이 하나로 정해지는 글자만 들어 있다. 표에 없는 글자는 그대로 둔다 — 틀리게 바꾸지 않는다.

규칙
  - 낱말 첫머리(앞이 글 시작·공백·기호)의 한자에는 두음법칙을 적용한다: 力 → 역, 女 → 여, 論 → 논.
  - 한글 음절 바로 뒤에 붙은 한자는 본음 그대로 쓴다: 답案 → 답안, 남女 → 남녀.
  - 앞 음절이 받침 없음·ㄴ 받침이면 렬·률은 열·율: 規律 → 규율, 序列 → 서열 (그 밖은 본음: 法律 → 법률).
  - allowed(질문·참고 문서에 있는 글자)는 인용일 수 있으므로 바꾸지 않는다.
한계: 앞 낱말이 접두어인 경우(신女性 → 신여성) 등 한국어 맞춤법의 예외는 판단하지 못한다.
      뜻이 아니라 음만 바꾼다. 한자의 문맥에 따른 읽기(예: 樂)는 표에 없으므로 바꾸지 않는다.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

TABLE_PATH = Path(__file__).resolve().parent / "static_data" / "hanja_ko.json"
_INITIAL_N, _INITIAL_R, _INITIAL_IEUNG = 2, 5, 11
_I_LIKE = {2, 6, 7, 12, 17, 20}          # ㅑ ㅕ ㅖ ㅛ ㅠ ㅣ — ㄴ·ㄹ 이 첫소리면 ㅇ 으로


@lru_cache(maxsize=1)
def load_table(path: Path = TABLE_PATH) -> dict[str, str]:
    return json.loads(path.read_text(encoding="utf-8"))["chars"]


def _is_hangul(ch: str) -> bool:
    return "가" <= ch <= "힣"


def _is_hanja(ch: str) -> bool:
    return "一" <= ch <= "鿿" or "㐀" <= ch <= "䶿"


def initial_sound_law(syllable: str) -> str:
    """낱말 첫머리의 한글 음절에 두음법칙을 적용한다 (녀→여, 력→역, 론→논 …)."""
    code = ord(syllable) - 0xAC00
    initial, rest = divmod(code, 21 * 28)
    medial, final = divmod(rest, 28)
    if initial == _INITIAL_N and medial in _I_LIKE:
        initial = _INITIAL_IEUNG
    elif initial == _INITIAL_R:
        initial = _INITIAL_IEUNG if medial in _I_LIKE else _INITIAL_N
    else:
        return syllable
    return chr(0xAC00 + (initial * 21 + medial) * 28 + final)


def _vowel_or_nieun_before(syllable: str) -> bool:
    """앞 음절이 받침이 없거나 ㄴ 받침인가 (이때 렬·률은 열·율 로 쓴다: 규율, 서열, 분열)."""
    return _is_hangul(syllable) and (ord(syllable) - 0xAC00) % 28 in (0, 4)


def to_hangul(text: str, allowed: str = "", table: dict[str, str] | None = None) -> tuple[str, int, list[str]]:
    """(바꾼 글, 바꾼 글자 수, 바꾸지 못하고 남은 한자 목록)."""
    table = load_table() if table is None else table
    out, converted, left = [], 0, []
    for i, ch in enumerate(text):
        reading = table.get(ch) if _is_hanja(ch) and ch not in allowed else None
        if reading is None:
            out.append(ch)
            if _is_hanja(ch) and ch not in allowed:
                left.append(ch)
            continue
        prev = text[i - 1] if i else ""
        word_start = not prev or not (_is_hangul(prev) or _is_hanja(prev) or prev.isalnum())
        if word_start:
            reading = initial_sound_law(reading)
        elif reading in ("렬", "률") and out and _vowel_or_nieun_before(out[-1]):
            reading = {"렬": "열", "률": "율"}[reading]
        out.append(reading)
        converted += 1
    return "".join(out), converted, list(dict.fromkeys(left))
