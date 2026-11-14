"""데이터시트 PDF(PyMuPDF)에서 핀 표(번호 → 이름)를 뽑는다. 정확도는 KiCad 심볼의 핀표와 대조해 잰다.

원칙: 추출 결과는 '제안'이다. 매핑 근거로 쓰기 전에 사람이 본다 (kicad_parts.propose_mapping 과 같은 승인 흐름).
- 표 한 줄에서 '핀 번호 칸'(7 · 5–12 · 24,23,22 같은 것)과 '이름 칸'(짧은 토큰)을 찾는다. 번호 칸이 이름 칸 앞에 있어도 뒤에 있어도 된다.
- 패키지별 번호 열이 여러 개면(TI 표) 첫 번째 번호 열만 쓴다(주 패키지).
- 버스 이름 ADBUS[7:0] 이 번호 목록에 대응하면 ADBUS7..ADBUS0 으로 풀어 번호 순서대로 맞춘다.
- 같은 핀이 여러 표에 다른 이름으로 나오면 먼저 나온 것을 쓴다.
"""
from __future__ import annotations

import re

import pymupdf

PIN_KEYWORDS = re.compile(
    r"pin[\s\-]*(functions?|descriptions?|configurations?|assignments?|names?|out|no\.?|numbers?|#)|pinning|terminal functions", re.I)
_DASHES = "–—−-"
_SPEC = re.compile(rf"^\d+(?:\s*(?:[,{_DASHES}]|to)\s*\d+)*$")
_NAME = re.compile(r"^[A-Za-z0-9~#_/+\-\.\[\]:\s]{1,18}$")
_BUS = re.compile(r"^([A-Za-z_]+)\[(\d+):(\d+)\]$")
_NOT_NAME = {"i", "o", "i/o", "io", "input", "output", "pwr", "power", "gnd_", "type", "name", "pin", "no", "no.", "na"}


def expand_spec(spec: str) -> list[int]:
    """'5–12' → [5..12], '24,23,22' → [24,23,22], '7' → [7]. 번호가 아니면 []."""
    s = re.sub(r"\s+", "", spec.replace("to", "–"))
    if not _SPEC.match(re.sub(r"\s+", "", spec)) and not re.match(rf"^\d+(?:[,{_DASHES}]\d+)*$", s):
        return []
    out: list[int] = []
    for part in s.split(","):
        pieces = re.split(rf"[{_DASHES}]", part)
        if len(pieces) == 2 and pieces[0] and pieces[1]:
            a, b = int(pieces[0]), int(pieces[1])
            if 0 < a <= b <= a + 80:
                out += list(range(a, b + 1))
        elif part.isdigit():
            out.append(int(part))
    return out


def normalize(name: str) -> str:
    """이름 비교용: 소문자 영숫자만 ('~{INT}/SQW' · 'INT/SQW' → 'intsqw')."""
    return re.sub(r"[^a-z0-9]", "", name.lower())


def _is_name(cell: str) -> bool:
    c = cell.strip()
    return bool(c) and bool(_NAME.match(c)) and not _SPEC.match(c) and c.lower() not in _NOT_NAME


def parse_row(cells: list[str]) -> list[tuple[int, str]]:
    """표 한 줄 → [(핀 번호, 이름)...]. 해석할 수 없으면 []."""
    cells = [re.sub(r"\s+", " ", (c or "").replace("\n", " ")).strip() for c in cells]
    cells = [c for c in cells if c]
    spec_i = next((i for i, c in enumerate(cells) if expand_spec(c)), None)
    if spec_i is None:
        return []
    # 주 패키지 열에 번호가 없고(—) 다른 패키지 열에만 있는 줄은 이 패키지의 핀이 아니다
    if any(re.fullmatch(rf"[{_DASHES}]+", c) for c in cells[:spec_i]):
        return []
    numbers = expand_spec(cells[spec_i])
    # 번호 칸에 가장 가까운 이름 칸: 먼저 앞쪽(이름-번호 순서), 없으면 뒤쪽
    before = [c for c in cells[:spec_i] if _is_name(c)]
    after = [c for c in cells[spec_i + 1:] if _is_name(c)]
    name = (before[-1] if before else (after[0] if after else ""))
    if not name:
        return []
    m = _BUS.match(name)
    if m and len(numbers) > 1:
        prefix, hi, lo = m.group(1), int(m.group(2)), int(m.group(3))
        indexes = list(range(hi, lo - 1, -1)) if hi >= lo else list(range(hi, lo + 1))
        if len(indexes) == len(numbers):
            return [(n, f"{prefix}{i}") for n, i in zip(numbers, indexes)]
    return [(n, name) for n in numbers]


_HEADER = re.compile(r"^(pin(\s*(no\.?|number|name|#))?|no\.?|number|name|signal|symbol|pin\s*name)$", re.I)


def has_header(rows: list[list[str]]) -> bool:
    """표 앞 4줄 안에 'Pin'·'Name'·'No.' 같은 머리글 칸이 있는가 (핀 번호처럼 보이는 숫자만 있는 엉뚱한 표 제외)."""
    for row in rows[:4]:
        for c in row:
            if c and _HEADER.match(re.sub(r"\s+", " ", c.replace("\n", " ")).strip()):
                return True
    return False


def pins_from_tables(tables: list[list[list[str]]]) -> dict[int, str]:
    """여러 표(행 목록)에서 핀 번호 → 이름. 같은 핀이 여러 번 나오면 먼저 나온 이름. 머리글 없는 표는 건너뛴다."""
    pins: dict[int, str] = {}
    for rows in tables:
        if not has_header(rows):
            continue
        # 첫 번호 열만: 한 줄에서 번호 칸이 여럿이면 parse_row 가 첫 번째를 쓴다
        for row in rows:
            for number, name in parse_row(row):
                pins.setdefault(number, name)
    return pins


GAP = 6.0   # 같은 줄에서 이 간격(pt)보다 벌어지면 다른 칸으로 본다 (낱말 사이 띄어쓰기는 보통 2~3pt)


def lines_as_rows(page) -> list[list[str]]:
    """표 인식이 실패한 쪽을 위한 대체: 단어 좌표로 줄을 만들고 간격이 큰 곳에서 칸을 나눈다 (위에서 아래 순서)."""
    words = page.get_text("words")  # x0, y0, x1, y1, text, block, line, word
    lines: list[list] = []
    for w in sorted(words, key=lambda w: ((w[1] + w[3]) / 2, w[0])):
        yc = (w[1] + w[3]) / 2
        if lines and abs(lines[-1][0] - yc) <= 3:
            lines[-1][1].append(w)
        else:
            lines.append([yc, [w]])
    rows = []
    for _, ws in lines:
        ws.sort(key=lambda w: w[0])
        cells, cur, last_x1 = [], [], None
        for w in ws:
            if cur and w[0] - last_x1 > GAP:
                cells.append(" ".join(x[4] for x in cur))
                cur = []
            cur.append(w)
            last_x1 = w[2]
        if cur:
            cells.append(" ".join(x[4] for x in cur))
        rows.append(cells)
    return rows


def rows_after_header(rows: list[list[str]], stop_after_misses: int = 3) -> list[list[str]]:
    """머리글 줄('Pin'·'Symbol'·'Name' 칸이 있는 줄) 아래 줄들. 핀으로 읽히지 않는 줄이 연달아 나오면 거기서 끝."""
    start = next((i for i, r in enumerate(rows) if has_header([r])), None)
    if start is None:
        return []
    out, hits, misses = [], 0, 0
    for r in rows[start + 1:]:
        if parse_row(r):
            out.append(r)
            hits += 1
            misses = 0
        else:
            misses += 1
            if hits and misses >= stop_after_misses:
                break
    return out


def candidate_pages(doc, max_pages: int = 12) -> list[int]:
    """핀 표가 있을 법한 쪽(0부터). 핀 관련 낱말이 있는 쪽을 앞에서부터."""
    pages = [i for i, pg in enumerate(doc) if PIN_KEYWORDS.search(pg.get_text())]
    return pages[:max_pages]


def extract_pins(pdf_path: str) -> dict[int, str]:
    doc = pymupdf.open(pdf_path)
    tables = []
    for i in candidate_pages(doc):
        found = [t.extract() for t in doc[i].find_tables().tables]
        tables += found
        # 표 인식이 이 쪽에서 핀을 하나도 못 읽었으면 단어 좌표로 다시 읽는다
        if not pins_from_tables(found):
            tables.append([["Pin"]] + rows_after_header(lines_as_rows(doc[i])))
    return pins_from_tables(tables)


def compare(extracted: dict[int, str], truth: list[dict]) -> dict:
    """KiCad 핀표(truth: [{'number','name'}...])와 대조: 번호·이름이 모두 같은 핀 수로 재현율·정밀도."""
    gt: dict[int, str] = {}
    for p in truth:
        # 이름이 비었거나 '~' 뿐인 핀(KiCad 게이트 심볼 등)은 이름 대조가 불가능하므로 채점에서 뺀다
        if str(p["number"]).isdigit() and normalize(p["name"]):
            gt[int(p["number"])] = p["name"]
    if not gt:
        return {"truth": 0, "extracted": len(extracted), "recall": None, "precision": None, "number_coverage": None}
    ok = [n for n, name in extracted.items() if n in gt and normalize(name) == normalize(gt[n])]
    nums = [n for n in extracted if n in gt]
    all_numbers = {int(p["number"]) for p in truth if str(p["number"]).isdigit()}
    spurious = [n for n in extracted if n not in all_numbers]   # 이 부품에 없는 핀 번호를 뽑은 것
    return {"truth": len(gt), "extracted": len(extracted), "matched": len(ok),
            "recall": round(len(ok) / len(gt), 3),
            "precision": round(len(ok) / len(nums), 3) if nums else 0.0,   # 정답 이름이 있는 핀 중 이름이 맞은 비율
            "spurious": len(spurious),
            "number_coverage": round(len(nums) / len(gt), 3)}
