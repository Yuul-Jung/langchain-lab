"""KiCad 공식 라이브러리와의 대응 검사 (G7).

- 심볼: 하네스 부품의 핀 번호 집합이 대응하는 KiCad 공식 심볼의 핀 번호 집합과 같은가.
        (이름이 다르면 WARN. 번호는 다르면 ERROR — 번호가 핀의 identity다)
- 풋프린트: 'Lib:Name' 파일이 실제로 있는가, 패드 번호가 심볼 핀 번호를 모두 덮는가.
라이브러리를 찾지 못하면 SKIPPED (PASS가 아니다). 경로: 환경변수 KICAD_SYMBOL_DIR /
KICAD_FOOTPRINT_DIR, 없으면 flatpak 확장(org.kicad.KiCad.Library.*)을 찾는다.
"""
from __future__ import annotations

import os
import re
import subprocess

from . import library, sexpr
from .checks import ERROR, F, WARN


def _flatpak_dir(ref, sub):
    try:
        r = subprocess.run(["flatpak", "info", "--user", "--show-location", ref],
                           capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if r.returncode != 0:
        return None
    d = os.path.join(r.stdout.strip(), "files", sub)
    return d if os.path.isdir(d) else None


def locate():
    sym = os.environ.get("KICAD_SYMBOL_DIR") or _flatpak_dir("org.kicad.KiCad.Library.Symbols", "symbols")
    fp = os.environ.get("KICAD_FOOTPRINT_DIR") or _flatpak_dir("org.kicad.KiCad.Library.Footprints", "footprints")
    sym = sym if sym and os.path.isdir(sym) else None
    fp = fp if fp and os.path.isdir(fp) else None
    return sym, fp


def _norm_pin(name):
    return re.sub(r"[~{}\s]", "", str(name)).upper()


def _symbol_text(lib_text, name):
    """라이브러리 텍스트에서 최상위 (symbol "name" ...) 한 덩어리를 괄호 균형으로 잘라낸다."""
    m = re.search(r'\n\t\(symbol "' + re.escape(name) + r'"\s', lib_text)
    if not m:
        return None
    i = m.start() + 1
    depth, j, in_str = 0, i, False
    while j < len(lib_text):
        c = lib_text[j]
        if in_str:
            if c == "\\":
                j += 1
            elif c == '"':
                in_str = False
        elif c == '"':
            in_str = True
        elif c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return lib_text[i:j + 1]
        j += 1
    return None


def _collect_pins(node, out):
    for x in node:
        if isinstance(x, list) and x:
            if x[0] == "pin":
                num, nm = sexpr.find(x, "number"), sexpr.find(x, "name")
                if num and len(num) > 1:
                    out.append((str(num[1]), str(nm[1]) if nm and len(nm) > 1 else ""))
            else:
                _collect_pins(x, out)


def symbol_pins(sym_dir, lib_id, _cache={}):
    """KiCad 심볼의 [(핀 번호, 핀 이름)]. extends는 기본 심볼에서 물려받는다. 없으면 None."""
    lib, name = lib_id.split(":", 1)
    path = os.path.join(sym_dir, f"{lib}.kicad_sym")
    if not os.path.isfile(path):
        return None
    if path not in _cache:
        with open(path, encoding="utf-8") as f:
            _cache[path] = f.read()
    for _ in range(4):                                 # extends 사슬
        txt = _symbol_text(_cache[path], name)
        if txt is None:
            return None
        node = sexpr.loads(txt)
        ext = sexpr.find(node, "extends")
        if not ext:
            pins = []
            _collect_pins(node, pins)
            return pins
        name = str(ext[1])
    return None


def pad_numbers(fp_dir, fp_id):
    """풋프린트의 패드 이름 집합(빈 이름 제외). 파일이 없으면 None."""
    if ":" not in fp_id:
        return None
    lib, name = fp_id.split(":", 1)
    path = os.path.join(fp_dir, f"{lib}.pretty", f"{name}.kicad_mod")
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as f:
        root = sexpr.loads(f.read())
    return {str(p[1]) for p in sexpr.find_all(root, "pad") if len(p) > 1 and str(p[1]) != ""}


def check(ir):
    """(상태, findings, metrics). 상태: PASS|FAIL|SKIPPED."""
    sym_dir, fp_dir = locate()
    if not sym_dir or not fp_dir:
        return "SKIPPED", [F("KICADLIB_NOT_FOUND", WARN,
                             "KiCad 심볼/풋프린트 라이브러리를 찾지 못해 대응 검사를 하지 못함 "
                             "(KICAD_SYMBOL_DIR/KICAD_FOOTPRINT_DIR 지정 또는 flatpak 확장 설치)")], {}
    out, seen_sym, seen_fp = [], set(), set()
    for c in ir["components"].values():
        part = library.get(c["part"])
        w = f"/components/{c['id']}"
        mine = {p.number: p.name for p in part.pins}
        if c["part"] not in seen_sym:
            seen_sym.add(c["part"])
            if not part.kicad_symbol:
                out.append(F("SYM_UNMAPPED", ERROR, f"{c['part']}: 대응 KiCad 심볼이 지정되지 않음", w))
            else:
                kp = symbol_pins(sym_dir, part.kicad_symbol)
                if kp is None:
                    out.append(F("SYM_NOT_FOUND", ERROR, f"{c['part']}: KiCad 심볼 {part.kicad_symbol} 없음", w))
                else:
                    ks = {n: nm for n, nm in kp}
                    if set(ks) != set(mine):
                        out.append(F("SYM_PIN_NUMBERS", ERROR,
                                     f"{c['part']}: 핀 번호가 KiCad {part.kicad_symbol}와 다름 "
                                     f"(하네스 {sorted(mine)} / KiCad {sorted(ks)})", w))
                    else:
                        for n in sorted(mine, key=lambda x: (len(x), x)):
                            a, b = _norm_pin(mine[n]), _norm_pin(ks[n])
                            if a not in ("", "~") and b not in ("", "~") and a != b:
                                out.append(F("SYM_PIN_NAME", WARN,
                                             f"{c['part']} 핀 {n}: 이름 '{mine[n]}' ≠ KiCad '{ks[n]}' "
                                             "(번호는 일치 — 표기 차이인지 확인)", w))
        if part.power_symbol:
            continue
        key = (c["part"], c["footprint"])
        if key in seen_fp:
            continue
        seen_fp.add(key)
        pads = pad_numbers(fp_dir, c["footprint"])
        if pads is None:
            out.append(F("FP_NOT_FOUND", ERROR, f"{c['ref']}: 풋프린트 {c['footprint']!r} 파일 없음", w))
            continue
        miss = sorted(set(mine) - pads)
        if miss:
            out.append(F("FP_PAD_MISSING", ERROR,
                         f"{c['ref']}: 심볼 핀 {miss}에 대응하는 패드가 풋프린트 {c['footprint']}에 없음", w))
        extra = sorted(pads - set(mine))
        if extra:
            out.append(F("FP_PAD_EXTRA", WARN,
                         f"{c['ref']}: 풋프린트 패드 {extra}에 대응하는 심볼 핀 없음 (실장 전용 패드인지 확인)", w))
    status = "FAIL" if any(f["severity"] == ERROR for f in out) else "PASS"
    return status, out, {"symbols_checked": len(seen_sym), "footprints_checked": len(seen_fp)}
