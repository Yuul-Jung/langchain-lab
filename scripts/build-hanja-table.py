#!/usr/bin/env python3
"""유니코드 한자 자료(Unihan)의 한글 음으로 한자→한글 음 표를 만든다.

사용: python scripts/build-hanja-table.py <Unihan_Readings.txt 경로> [출력 경로]
  Unihan 은 https://www.unicode.org/Public/UCD/latest/ucd/Unihan.zip 에서 내려받는다(공개 자료, 개인 정보 없음).

표에 넣는 글자: 음이 하나로 정해지는 글자만.
  - 한글 음이 하나뿐인 글자
  - 음이 여럿이어도 서로 두음법칙 차이일 뿐인 글자 (力: 력·역 → 력)
  음이 정말 여럿인 글자(樂 락·악·요, 行 항·행, 說 설·세·열)는 넣지 않는다.
  (시험에서 '표준 음 표시 E 가 하나뿐이면 고른다'는 기준은 樂 → 낙기 처럼 틀려 버려졌다.)
  틀리게 바꾸느니 그대로 둔다.
두음법칙(力 → 역)은 표가 아니라 hanja_ko.py 가 낱말 첫머리에서만 적용한다. 표에는 본음(력)을 둔다.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from hanja_ko import initial_sound_law  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = ROOT / "static_data" / "hanja_ko.json"
LINE = re.compile(r"^U\+([0-9A-F]+)\tkHangul\t(.+)$")
LICENSE = "Unicode License v3 (https://www.unicode.org/license.txt)"


def pick_reading(field: str) -> str | None:
    """'력:0E 역:0' 같은 값에서 하나로 정해지는 음. 정할 수 없으면 None."""
    readings = list(dict.fromkeys(part.split(":", 1)[0] for part in field.split()))
    # 다른 음의 두음법칙형(력 → 역)은 같은 음으로 본다
    distinct = [r for r in readings
                if not (len(r) == 1 and any(o != r and len(o) == 1 and initial_sound_law(o) == r for o in readings))]
    return distinct[0] if len(distinct) == 1 else None


def build(readings_path: Path) -> dict:
    version = ""
    chars, ambiguous = {}, 0
    for line in readings_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("# Unicode Version"):
            version = line.split()[-1]
        m = LINE.match(line)
        if not m:
            continue
        reading = pick_reading(m.group(2))
        if reading is None:
            ambiguous += 1
        elif len(reading) == 1 and "가" <= reading <= "힣":
            chars[chr(int(m.group(1), 16))] = reading
    return {"source": "Unihan kHangul", "unicode_version": version, "license": LICENSE,
            "excluded_ambiguous": ambiguous, "chars": dict(sorted(chars.items()))}


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    table = build(Path(sys.argv[1]))
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_OUT
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(table, ensure_ascii=False, indent=0), encoding="utf-8")
    print(f"표 {len(table['chars'])}자, 음이 하나로 정해지지 않아 뺀 글자 {table['excluded_ambiguous']}자 → {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
