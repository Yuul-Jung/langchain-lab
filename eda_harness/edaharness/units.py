"""SI 접두사 표기와 E-series 값 선택."""
from __future__ import annotations

import math
import re

E24 = (1.0, 1.1, 1.2, 1.3, 1.5, 1.6, 1.8, 2.0, 2.2, 2.4, 2.7, 3.0,
       3.3, 3.6, 3.9, 4.3, 4.7, 5.1, 5.6, 6.2, 6.8, 7.5, 8.2, 9.1)
E6 = (1.0, 1.5, 2.2, 3.3, 4.7, 6.8)

_PREFIX = [(1e9, "G"), (1e6, "M"), (1e3, "k"), (1.0, ""), (1e-3, "m"),
           (1e-6, "u"), (1e-9, "n"), (1e-12, "p")]
_PARSE = {"G": 1e9, "M": 1e6, "k": 1e3, "K": 1e3, "": 1.0, "m": 1e-3,
          "u": 1e-6, "µ": 1e-6, "n": 1e-9, "p": 1e-12}


def _series_values(series, lo_exp=-12, hi_exp=9):
    for e in range(lo_exp, hi_exp + 1):
        for m in series:
            yield round(m * 10 ** e, 15)


def e_nearest(value: float, series=E24, mode: str = "nearest") -> float:
    """E-series 값 선택. mode: nearest | ceil | floor."""
    if value <= 0 or not math.isfinite(value):
        raise ValueError(f"E-series 선택 불가 값: {value}")
    cands = list(_series_values(series))
    if mode == "ceil":
        return min(v for v in cands if v >= value * (1 - 1e-9))
    if mode == "floor":
        return max(v for v in cands if v <= value * (1 + 1e-9))
    return min(cands, key=lambda v: abs(math.log(v / value)))


def format_si(value: float, unit: str = "") -> str:
    """4700 -> '4.7k', 1e-5 -> '10u'. KiCad Value 필드 관례."""
    if value == 0:
        return "0" + unit
    for scale, p in _PREFIX:
        if abs(value) >= scale * (1 - 1e-9):
            num = value / scale
            s = f"{num:.3g}"
            if "e" in s:
                s = f"{num:.0f}"
            return f"{s}{p}{unit}"
    return f"{value:.3g}{unit}"


_SI_RE = re.compile(r"^\s*([0-9]*\.?[0-9]+)\s*([GMkKmuµnp]?)\s*([A-Za-zΩ]*)\s*$")


def parse_si(text: str) -> float:
    m = _SI_RE.match(text)
    if not m:
        raise ValueError(f"SI 값 해석 불가: {text!r}")
    return float(m.group(1)) * _PARSE[m.group(2)]


def rail_name(voltage: float) -> str:
    """3.3 -> '+3V3', 5 -> '+5V', 12 -> '+12V'."""
    if voltage <= 0:
        raise ValueError("레일 전압은 양수여야 한다")
    whole = int(math.floor(voltage + 1e-9))
    frac = round(voltage - whole, 3)
    if frac < 1e-6:
        return f"+{whole}V"
    digits = f"{frac:.3f}"[2:].rstrip("0")
    return f"+{whole}V{digits}"


def cap_voltage_rating(net_v: float, factor: float = 1.5) -> float:
    for r in (6.3, 10, 16, 25, 35, 50, 63, 100):
        if r >= net_v * factor:
            return r
    raise ValueError(f"{net_v}V에 맞는 표준 커패시터 정격 없음")


def divider_window(v_lo: float, v_hi: float, r_top: float, r_bot: float, r_tol: float):
    """저항 분압기 출력 전압의 최악 범위 (입력 v_lo~v_hi, 저항 허용오차 r_tol).

    반환: (출력 최소 V, 출력 최대 V). 최소는 위쪽 저항이 크고 아래쪽이 작을 때,
    최대는 그 반대일 때다. 합성기와 G3 검사가 같은 식을 쓴다.
    """
    lo = v_lo * r_bot * (1 - r_tol) / (r_bot * (1 - r_tol) + r_top * (1 + r_tol))
    hi = v_hi * r_bot * (1 + r_tol) / (r_bot * (1 + r_tol) + r_top * (1 - r_tol))
    return lo, hi


def rc_rise_time(r_top: float, r_bot: float, c_load: float) -> float:
    """분압기 출력의 10~90% 상승 시간 근사 (2.2·R_th·C)."""
    return 2.2 * (r_top * r_bot / (r_top + r_bot)) * c_load


# ---- 길이: 사용자는 mil과 mm를 모두 쓴다. 내부 기준은 mm (KiCad 파일 단위).
MM_PER_MIL = 0.0254
_LEN_RE = re.compile(r"^\s*([0-9]*\.?[0-9]+)\s*(mil|mils|thou|mm|in|inch)\s*$", re.I)


def mil_to_mm(mil: float) -> float:
    return mil * MM_PER_MIL


def mm_to_mil(mm: float) -> float:
    return mm / MM_PER_MIL


def parse_length_mm(text: str) -> float:
    """'100mil' / '2.54 mm' / '0.1in' -> mm. 단위가 없으면 오류(모호한 길이는 받지 않는다)."""
    m = _LEN_RE.match(text)
    if not m:
        raise ValueError(f"길이 해석 불가(단위 mil|mm|in 필요): {text!r}")
    v, u = float(m.group(1)), m.group(2).lower()
    return v if u == "mm" else v * 25.4 if u in ("in", "inch") else mil_to_mm(v)


def format_length(mm: float) -> str:
    """같은 길이를 'mm (mil)' 두 단위로 표기."""
    return f"{mm:.4g}mm ({mm_to_mil(mm):.4g}mil)"
