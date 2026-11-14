"""보드 정보: 핀 연결표 + 데이터시트 인용 -> 받는 쪽 신호 사양.

- 핀 연결표는 어떤 형식에서 읽었든 같은 모양({헤더: [{sch, fpga_pin, iostandard, port}]})이면 된다.
  parse_xdc는 그 읽기 방법(importer) 중 하나일 뿐이며, 프로파일을 만드는 쪽은 특정 도구·형식을 모른다.
- 구조화된 표는 LLM 없이 코드로 읽는다.
- 데이터시트 값은 '원문 인용(quote)'과 함께 제안(proposed)으로만 만들어지고, 프로그램이
  인용문이 실제 문서 텍스트에 있고 제안한 숫자가 그 인용문에 있는지 검사한다(어긋나면 거절).
- 사용자가 승인(approved)해야 basis='datasheet'가 된다. 승인 전에는 basis='assumed'.
"""
from __future__ import annotations

import re

_LINE_RE = re.compile(r"^\s*#?\s*set_property\b(?P<body>.*)$")
_PKG_RE = re.compile(r"PACKAGE_PIN\s+(\w+)")
_IOS_RE = re.compile(r"IOSTANDARD\s+(\w+)")
_PORT_RE = re.compile(r"get_ports\s*\{?\s*([^\s{}]+?)\s*\}?\s*\]\s*;?\s*(?:#|$)")
_SCH_RE = re.compile(r"#.*?\bSch\s*(?:name\s*)?=\s*([A-Za-z0-9_\[\]]+)", re.I)
_HDR_RE = re.compile(r"^\s*##\s*Pmod\s+Header\s+(\w+)", re.I)


class BoardError(Exception):
    pass


def _label(raw):
    """'ja[1]' / 'JA1' / 'JA[0]' 형태의 표기를 대문자 'JA1' 식으로 정규화."""
    return re.sub(r"[\[\]]", "", raw).upper()


def parse_xdc(text: str) -> dict:
    """{ 헤더: [ {sch, fpga_pin, iostandard, port} ] } — 'Pmod Header' 구역만.

    제조사마다 공백·주석 표기가 달라서(예: 'Sch name = JA1' / 'Sch=ja[1]') 핵심 토큰(PACKAGE_PIN,
    IOSTANDARD, get_ports)만 읽는다. 신호 라벨은 Sch 주석이 있으면 그것, 없으면 포트 이름.
    구역 안의 PACKAGE_PIN 줄 수와 읽은 핀 수가 다르면 형식을 모르는 것이므로 오류(조용히 빠뜨리지 않음).
    """
    out, raw_count, cur = {}, {}, None
    for line in text.splitlines():
        h = _HDR_RE.match(line)
        if h:
            cur = h.group(1)
            out[cur], raw_count[cur] = [], 0
            continue
        if line.lstrip().startswith("##"):
            cur = None
            continue
        if cur is None or not _LINE_RE.match(line):
            continue
        if "PACKAGE_PIN" not in line:
            continue
        raw_count[cur] += 1
        body = line
        pk, ios, port = _PKG_RE.search(body), _IOS_RE.search(body), _PORT_RE.search(body)
        if not (pk and ios and port):
            continue
        sch = _SCH_RE.search(body)
        out[cur].append({"sch": _label(sch.group(1) if sch else port.group(1)), "fpga_pin": pk.group(1),
                         "iostandard": ios.group(1), "port": port.group(1)})
    for h, pins in out.items():
        if len(pins) != raw_count[h]:
            raise BoardError(f"헤더 {h}: PACKAGE_PIN {raw_count[h]}줄 중 {len(pins)}줄만 읽음 — 알 수 없는 형식")
    return out


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def verify_evidence(doc_text: str, quote: str, numbers) -> None:
    """인용문이 문서에 그대로 있고, 제안한 숫자가 인용문 안에 있어야 한다. 아니면 BoardError."""
    if _norm(quote) not in _norm(doc_text):
        raise BoardError(f"인용문이 문서에 없음: {quote[:60]!r}")
    toks = set(re.findall(r"[-–]?\d+(?:\.\d+)?", quote))
    for n in numbers:
        if not any(abs(float(t.replace("–", "-")) - n) < 1e-9 for t in toks):
            raise BoardError(f"숫자 {n}이(가) 인용문에 없음: {quote[:60]!r}")


def page_of(doc_text: str, quote: str):
    q = _norm(quote)
    for i, p in enumerate(doc_text.split("\f"), 1):
        if q in _norm(p):
            return i
    return None


def build_profile(name, pins, pins_source, ds_text, ds_source, items, digital_headers, shared_headers=()):
    """items: [{key, value, quote, locator, quote_number?}] — 값은 데이터시트에서 제안된 것.
    quote_number는 인용문에 적힌 숫자(단위 환산 전, 없으면 value). 인용문과 숫자가 verify_evidence를 통과해야 한다."""
    hdrs = parse_xdc(pins) if isinstance(pins, str) else pins      # 문자열=XDC 텍스트, 아니면 이미 읽은 표
    signals, spec = {}, {}
    for it in items:
        verify_evidence(ds_text, it["quote"], [it.get("quote_number", it["value"])])
        spec[it["key"]] = {"value": it["value"], "quote": _norm(it["quote"]), "locator": it["locator"],
                           "pdf_page": page_of(ds_text, it["quote"])}
    for h in list(digital_headers) + list(shared_headers):
        if h not in hdrs or not hdrs[h]:
            raise BoardError(f"핀 연결표에 헤더 {h} 없음")
        for p in hdrs[h]:
            if p["iostandard"] != "LVCMOS33":
                raise BoardError(f"{p['sch']}: LVCMOS33이 아님({p['iostandard']}) — 사양 매핑 없음")
            signals[p["sch"]] = {"header": h, "fpga_pin": p["fpga_pin"], "iostandard": p["iostandard"],
                                 "class": "digital" if h in digital_headers else "shared_xadc"}
    return {"name": name, "review_status": "proposed", "pins_source": pins_source,
            "datasheet_source": ds_source, "input_spec": spec, "signals": signals,
            "headers_found": sorted(hdrs)}


def approve(profile, reviewer_note):
    if not reviewer_note or not reviewer_note.strip():
        raise BoardError("승인에는 검토 사유가 필요함")
    out = dict(profile)
    out["review_status"] = "approved"
    out["reviewer_note"] = reviewer_note.strip()
    return out


def sink_part(profile, sig_name):
    """ratings.level_link_block의 받는 쪽 입력 형식으로 변환. 'GPIO' 핀 하나를 돌려준다."""
    s = profile["signals"].get(sig_name)
    if s is None:
        raise BoardError(f"보드에 신호 {sig_name} 없음 (있는 헤더: {profile['headers_found']})")
    ok = profile["review_status"] == "approved"
    basis = "datasheet" if ok else "assumed"
    spec = profile["input_spec"]
    for k in ("vih_min_v", "vmax_v", "cin_f"):
        if k not in spec:
            raise BoardError(f"입력 사양 {k} 없음")

    def ent(k):
        e = spec[k]
        return {"value": e["value"], "basis": basis,
                "note": f"{e['locator']} (pdf p.{e['pdf_page']}): {e['quote']}" + ("" if ok else " — 승인 전 제안")}
    return {"name": f"{profile['name']} {sig_name}({s['header']}, FPGA {s['fpga_pin']})",
            "signals": {"GPIO": {k: ent(k) for k in ("vih_min_v", "vmax_v", "cin_f")}}}
