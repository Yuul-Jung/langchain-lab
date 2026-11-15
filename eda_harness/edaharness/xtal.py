"""크리스탈 발진회로(피어스, 인버터형 증폭기 + 크리스탈 + 부하 커패시터 2개)의 설계 계산과 검증.

결정적이고 fail-closed: 입력 값마다 근거(basis)가 있어야 하고, 없거나 숫자가 아니면 계산하지 않고 거절한다.
LLM이 하기 쉬운 '값 지어내기'를 막는 것이 목적이라 부품 이름은 보지 않고 숫자만 읽는다.

입력(모두 {"value": 숫자, "basis": datasheet|derived|assumed, "note": 선택}):
  크리스탈: f_hz(공진 주파수) · cl_f(부하 용량 CL) · esr_ohm(등가 직렬 저항) · c0_f(병렬 용량)
  증폭기:   gm_s(보장되는 최소 상호 컨덕턴스, 이 전원·주파수에서)
  회로:     cstray_f(핀 용량+배선 용량의 합, 각 커패시터 쪽 기준)
공식(출처: 크리스탈 발진기 설계의 일반 관례, 값 자체는 부품 데이터시트에서 와야 함)
  부하 커패시터 같은 값 C1 = C2 = C 일 때  CL = C/2 + cstray  →  C = 2·(CL − cstray)
  임계 상호 컨덕턴스  gm_crit = 4 · ESR · (2π f)² · (C0 + CL)²
  이득 여유 = gm / gm_crit  (권장 5 이상)
검증하지 않는 것(표시만 한다): 구동 전력(drive level)은 증폭기 출력 진폭이 필요해 계산하지 않는다 → DRIVE_LEVEL_NOT_CHECKED 경고.
"""
from __future__ import annotations

import math

from . import units

BASES = ("datasheet", "derived", "assumed")
CRYSTAL_KEYS = {"f_hz": "공진 주파수(Hz)", "cl_f": "부하 용량 CL(F)", "esr_ohm": "등가 직렬 저항 ESR(Ω)", "c0_f": "병렬 용량 C0(F)"}
IC_KEYS = {"gm_s": "증폭기 보장 상호 컨덕턴스(S)"}
CIRCUIT_KEYS = {"cstray_f": "핀·배선 용량 합(F)"}
MARGIN_MIN = 5.0          # 이득 여유 최소(권장값)
MARGIN_OK = 10.0          # 이 이상이면 경고 없음
CL_TOL = 0.15             # 실제 CL 이 목표에서 벗어나도 되는 비율


class XtalError(Exception):
    pass


def _read(group: dict, keys: dict, role: str, findings: list):
    """근거가 붙은 숫자만 읽는다. 없으면 XtalError(fail-closed). 근거가 datasheet 가 아니면 경고를 남긴다."""
    out = {}
    for k, label in keys.items():
        e = (group or {}).get(k)
        if not isinstance(e, dict) or "value" not in e:
            raise XtalError(f"{role}: {label}({k}) 값이 없음")
        v = e["value"]
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v <= 0:
            raise XtalError(f"{role}: {k} 는 0보다 큰 숫자여야 함")
        if e.get("basis") not in BASES:
            raise XtalError(f"{role}: {k} 의 근거(basis)는 {BASES} 중 하나여야 함")
        out[k] = float(v)
        if e["basis"] != "datasheet":
            findings.append({"severity": "WARN", "code": "UNVERIFIED_BASIS", "field": f"{role}.{k}",
                             "msg": f"{label} = {v:g} 은 {e['basis']} 값(데이터시트 미확인): {e.get('note') or '사유 미기재'}"})
    return out


def gm_crit(f_hz: float, esr_ohm: float, c0_f: float, cl_f: float) -> float:
    return 4.0 * esr_ohm * (2.0 * math.pi * f_hz) ** 2 * (c0_f + cl_f) ** 2


def cl_of(c1_f: float, c2_f: float, cstray_f: float) -> float:
    """직렬로 보이는 부하 용량. C1·C2 가 다르면 직렬 합성, 핀·배선 용량은 더한다."""
    return (c1_f * c2_f) / (c1_f + c2_f) + cstray_f


def verify(crystal: dict, ic: dict, circuit: dict, c1_f: float, c2_f: float) -> dict:
    """이미 정해진 C1·C2 를 부품 값에서 **다시 계산**해 판정한다(합성기가 적은 값을 믿지 않음).
    반환: {"cl_actual_f","gm_crit_s","margin","findings"}. findings 에 ERROR 가 없으면 통과."""
    findings: list = []
    x = _read(crystal, CRYSTAL_KEYS, "크리스탈", findings)
    i = _read(ic, IC_KEYS, "증폭기", findings)
    c = _read(circuit, CIRCUIT_KEYS, "회로", findings)
    for name, v in (("c1_f", c1_f), ("c2_f", c2_f)):
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v <= 0:
            raise XtalError(f"{name} 는 0보다 큰 숫자여야 함")
    cl_actual = cl_of(c1_f, c2_f, c["cstray_f"])
    err = (cl_actual - x["cl_f"]) / x["cl_f"]
    if abs(err) > CL_TOL:
        findings.append({"severity": "ERROR", "code": "LOAD_CAP_MISMATCH", "field": "cl",
                         "msg": f"실제 부하 용량 {cl_actual * 1e12:.1f}pF 가 크리스탈 CL {x['cl_f'] * 1e12:.1f}pF 와 "
                                f"{abs(err) * 100:.0f}% 다름(허용 {CL_TOL * 100:.0f}%) → 주파수 오차·발진 불안정"})
    gc = gm_crit(x["f_hz"], x["esr_ohm"], x["c0_f"], cl_actual)
    margin = i["gm_s"] / gc
    if margin < MARGIN_MIN:
        findings.append({"severity": "ERROR", "code": "GAIN_MARGIN", "field": "gm",
                         "msg": f"이득 여유 {margin:.1f} 이 최소 {MARGIN_MIN:g} 보다 작음(증폭기 gm {i['gm_s'] * 1e3:.2f}mS, "
                                f"필요 gm_crit {gc * 1e3:.3f}mS) → 시동 실패 위험"})
    elif margin < MARGIN_OK:
        findings.append({"severity": "WARN", "code": "GAIN_MARGIN_LOW", "field": "gm",
                         "msg": f"이득 여유 {margin:.1f} (권장 {MARGIN_OK:g} 이상 여유 있음)"})
    findings.append({"severity": "WARN", "code": "DRIVE_LEVEL_NOT_CHECKED", "field": "drive",
                     "msg": "구동 전력(drive level)은 증폭기 출력 진폭이 필요해 검사하지 않음 — 크리스탈 최대 구동 전력과 직접 대조 필요(미검증)"})
    return {"cl_actual_f": cl_actual, "gm_crit_s": gc, "margin": margin, "findings": findings}


def design(crystal: dict, ic: dict, circuit: dict, series=units.E24) -> dict:
    """같은 값 C1 = C2 = C 로 설계하고, 고른 값을 verify 로 다시 계산해 돌려준다.
    목표 CL − cstray 가 0 이하이면(핀 용량만으로 CL 을 넘음) 설계 불가로 거절한다."""
    probe: list = []
    x = _read(crystal, CRYSTAL_KEYS, "크리스탈", probe)
    c = _read(circuit, CIRCUIT_KEYS, "회로", probe)
    c_target = 2.0 * (x["cl_f"] - c["cstray_f"])
    if c_target <= 0:
        raise XtalError(f"핀·배선 용량 {c['cstray_f'] * 1e12:.1f}pF 가 크리스탈 CL {x['cl_f'] * 1e12:.1f}pF 이상이라 같은 값 부하 커패시터로 설계할 수 없음")
    c_pick = units.e_nearest(c_target, series, mode="nearest")
    res = verify(crystal, ic, circuit, c_pick, c_pick)
    res.update({"c1_f": c_pick, "c2_f": c_pick, "c_target_f": c_target})
    return res


def passes(findings: list) -> bool:
    return not any(f["severity"] == "ERROR" for f in findings)
