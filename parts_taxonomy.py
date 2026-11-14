"""부품 분류 체계의 공통 규칙: 종류(kind), 도메인별 허용 종류, 파생 축(재료·회로 성격), 이름 규칙 맞추기.

분류 체계 파일(static_data/parts_taxonomy.json)의 기능마다 kind 를 저장한다. 재료·회로 성격은 kind 와 도메인에서 계산하고 저장하지 않는다.
검사기(scripts/check-parts-taxonomy.py)와 화면 생성기(scripts/build-parts-tree.py)가 이 모듈 하나를 함께 쓴다.
"""
from __future__ import annotations

KINDS = ("ic", "discrete", "passive", "electromech", "module", "mechanical", "symbol", "tube")
KIND_KO = {"ic": "집적회로(IC)", "discrete": "개별 반도체", "passive": "수동 소자", "electromech": "전기기계",
           "module": "모듈·조립품", "mechanical": "기구", "symbol": "회로도 기호", "tube": "진공관"}
# 도메인마다 허용되는 종류. 한 종류뿐인 도메인(passive·discrete·connect·boards·memory·interface)은 다른 종류가 들어오면 충돌이다.
DOMAIN_KINDS = {
    "processor": {"ic", "module"}, "analog": {"ic", "electromech"}, "power": {"ic", "module", "discrete", "electromech"},
    "logic": {"ic", "module", "passive"}, "memory": {"ic"}, "interface": {"ic"}, "rf": {"ic", "module", "passive"},
    "sensor": {"ic", "passive"}, "discrete": {"discrete"}, "opto": {"discrete", "module", "electromech"},
    "electromech": {"electromech", "module", "mechanical"}, "protection": {"discrete", "passive"}, "passive": {"passive"},
    "connect": {"mechanical"}, "boards": {"module"}, "other": {"ic", "symbol", "tube"},
}
# 새 기능을 처음 만들 때 쓰는 기본값(저장된 값이 원본이다)
DOMAIN_DEFAULT_KIND = {"processor": "ic", "analog": "ic", "power": "ic", "logic": "ic", "memory": "ic", "interface": "ic", "rf": "ic",
                       "sensor": "ic", "discrete": "discrete", "opto": "discrete", "electromech": "electromech", "protection": "passive",
                       "passive": "passive", "connect": "mechanical", "boards": "module", "other": "ic"}
FUNCTION_KIND = {
    "module": "module", "microphone": "electromech", "dcdc_module": "module", "acdc": "module", "solar": "discrete",
    "battery_cell": "electromech", "oscillator": "module", "crystal": "passive", "delay": "passive", "rf_module": "module",
    "antenna": "passive", "rf_filter": "passive", "thermistor": "passive", "fiber": "module", "lcd_char": "module",
    "lcd_graphic": "module", "lamp": "electromech", "ssr": "module", "thermal": "mechanical", "tvs": "discrete",
    "dev_board": "module", "schematic_symbol": "symbol", "vacuum_tube": "tube",
}


def default_kind(function_id: str, domain: str) -> str:
    return FUNCTION_KIND.get(function_id) or DOMAIN_DEFAULT_KIND[domain]


# ---- 파생 축(저장하지 않는다)
MATERIAL_KO = {"semiconductor": "반도체", "non_semiconductor": "비반도체", "assembly": "조립품(모듈)"}
NATURE_KO = {"analog": "아날로그", "power": "전원", "digital": "디지털", "mixed_signal": "혼합 신호", "unspecified": "기타"}
_NATURE = {"analog": "analog", "power": "power", "processor": "digital", "logic": "digital", "memory": "digital",
           "interface": "mixed_signal", "rf": "mixed_signal", "sensor": "mixed_signal"}


def material(kind: str) -> str:
    if kind in ("ic", "discrete"):
        return "semiconductor"
    if kind == "module":
        return "assembly"
    return "non_semiconductor"


def circuit_nature(kind: str, domain: str) -> str | None:
    """IC 만 회로 성격이 있다(아날로그·전원·디지털·혼합 신호). 그 밖의 종류는 None."""
    return _NATURE.get(domain, "unspecified") if kind == "ic" else None


def tech_group(kind: str, domain: str) -> tuple[str, str]:
    """기술 보기의 묶음 (대분류, 소분류) 한국어 이름."""
    m = material(kind)
    if kind == "ic":
        return MATERIAL_KO[m], "IC · " + NATURE_KO[circuit_nature(kind, domain)]
    if kind == "discrete":
        return MATERIAL_KO[m], "개별 소자"
    if kind == "module":
        return MATERIAL_KO[m], "모듈"
    return MATERIAL_KO[m], KIND_KO[kind]


def match_rule(rules: dict, name: str, seps: str = "_"):
    """이름이 키와 같거나 '키+구분자'로 시작하면 그 규칙(긴 키 먼저). 'R' 이 'RotaryEncoder' 를 삼키지 않는다."""
    keys = sorted((k for k in rules if k != "*"), key=len, reverse=True)
    k = next((k for k in keys if name == k or any(name.startswith(k + s) for s in seps)), None)
    return rules.get(k) if k else rules.get("*")
