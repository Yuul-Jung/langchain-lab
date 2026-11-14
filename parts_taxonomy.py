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


# ---------------------------------------------------------------- 검색에서 분류 체계 쓰기
import json
import re
from pathlib import Path

TAXONOMY_PATH = Path(__file__).resolve().parent / "static_data" / "parts_taxonomy.json"
KIND_SHORT = {"ic": "IC", "discrete": "개별 반도체", "passive": "수동 소자", "electromech": "전기기계", "module": "모듈",
              "mechanical": "기구", "symbol": "기호", "tube": "진공관"}
_GENERIC_KO = {"로직", "센서", "모듈", "변환", "기타", "특수", "일반", "시계", "소자", "보호", "필터", "ic", "칩", "부품"}   # 너무 흔해 기능을 가르지 못하는 낱말
_cache: dict = {}


class Taxonomy:
    """분류 체계 파일을 검색에서 쓰는 도우미: 부품 → 기능, 질문 → 목표 기능, 경로 이름."""

    def __init__(self, data: dict):
        self.d = data
        self.funcs = {f["id"]: f for f in data["functions"]}
        self.domains = {x["id"]: x for x in data["domains"]}
        self.libs = data["libraries"]
        self.generic = data["generic"]
        self.evidence = {k: re.compile(v, re.I) for k, v in (data.get("function_evidence") or {}).items() if k != "_note"}

    @classmethod
    def load(cls, path: Path | None = None) -> "Taxonomy | None":
        """파일이 없거나 깨졌으면 None(검색은 분류 체계 없이 그대로). 파일이 바뀌면 다시 읽는다."""
        path = path or TAXONOMY_PATH
        try:
            m = path.stat().st_mtime
            if _cache.get("key") != (str(path), m):
                _cache["tax"], _cache["key"] = cls(json.loads(path.read_text(encoding="utf-8"))), (str(path), m)
            return _cache["tax"]
        except Exception:
            return None

    # --- 부품 → 기능
    def library_functions(self, lib: str) -> list[str]:
        e = self.libs.get(lib)
        if not e:
            return sorted({r["function"] for r in self.generic.get(lib, {}).values()})
        out = [e["function"]] + list(e.get("also_functions", [])) + [r["function"] for r in (e.get("part_rules") or {}).values()]
        return list(dict.fromkeys(out))

    def classify(self, lib: str, name: str, text: str = "") -> dict | None:
        """{'function','domain','kind','mixed','by'} 또는 None(분류 체계에 없는 라이브러리·규칙 없는 일반 분류 부품).
        우선순위: 부분 이름 규칙 > (혼합 라이브러리) 설명 증거 > 대표 기능."""
        e = self.libs.get(lib)
        if e is None:
            r = match_rule(self.generic.get(lib, {}), name) if lib in self.generic else None
            return self._info(r["function"], False, "이름 규칙") if r else None
        pr = e.get("part_rules") or {}
        r = match_rule(pr, name, "_-") if pr else None
        if r:
            return self._info(r["function"], bool(e.get("mixed")), "이름 규칙")
        if e.get("mixed") and text:
            # 설명의 첫 구절(쉼표·세미콜론·괄호 앞)에서, 가장 뒤에 나오는 증거가 부품의 머리말(영어는 명사구의 끝이 머리)이다:
            # 'step-down DC/DC power module' → module, 'quad 2-input NAND gate' → gate.  첫 구절에 증거가 없으면 전체 글에서 같은 규칙.
            first = re.split(r"[,;(]", text, maxsplit=1)[0]
            for scope in (first, text):
                best = None
                for fid in [e["function"]] + list(e.get("also_functions", [])):
                    rx = self.evidence.get(fid)
                    ends = [m.end() for m in rx.finditer(scope)] if rx else []
                    if ends and (best is None or max(ends) > best[0]):
                        best = (max(ends), fid)
                if best:
                    return self._info(best[1], True, "설명 증거")
        return self._info(e["function"], bool(e.get("mixed")), "대표 기능")

    def _info(self, fid: str, mixed: bool, by: str) -> dict:
        f = self.funcs[fid]
        return {"function": fid, "domain": f["domain"], "kind": f["kind"], "mixed": mixed, "by": by}

    def label(self, info: dict) -> str:
        """'전원 › 선형 레귤레이터(LDO) · IC' (혼합 라이브러리면 ' · 혼합 라이브러리')."""
        f = self.funcs[info["function"]]
        s = f"{self.domains[f['domain']]['ko']} › {f['ko']} · {KIND_SHORT[f['kind']]}"
        return s + " · 혼합 라이브러리" if info.get("mixed") else s

    # --- 질문 → 목표 기능
    def targets(self, query: str, libraries) -> set[str]:
        """질문(영어 낱말 포함)과 맞는 기능 중, 개념의 라이브러리가 가진 기능만. 맞는 것이 없으면 빈 집합(분류 체계 순위 안 씀)."""
        cand = {fid for lib in libraries for fid in self.library_functions(lib)}
        out = set()
        for fid in cand:
            rx = self.evidence.get(fid)
            if rx and rx.search(query):
                out.add(fid); continue
            toks = [t for t in re.split(r"[·()\s,/]+", self.funcs[fid]["ko"]) if len(t) >= 2 and t not in _GENERIC_KO]
            if any(t in query for t in toks):
                out.add(fid)
        return out

    # --- 질문에서 기능 찾기(개념 사전에 없는 말도 우리 분류 체계의 이름으로 찾는다)
    def aliases(self) -> list[tuple[str, str]]:
        """[(낱말, 기능 id)] — 낱말의 출처는 분류 체계 파일뿐: 기능의 한국어 이름 토막, 부분 이름 규칙·일반 분류 규칙의 한국어 이름('냉각 팬'
        '개발 보드' …), 부분 이름 규칙의 키(NUCLEO·Arduino 같은 카탈로그 이름). 질문 문장에서 따온 낱말은 없다."""
        if "aliases" in _cache:
            return _cache["aliases"]
        out: list[tuple[str, str]] = []

        def add(word: str, fid: str):
            w = word.strip().lower()
            if len(w) >= 2 and w not in _GENERIC_KO:
                out.append((w, fid))
        for fid, f in self.funcs.items():
            for tok in re.split(r"[·()\s,/]+", f["ko"]):
                add(tok, fid)
        for lib, e in self.libs.items():
            for key, r in (e.get("part_rules") or {}).items():
                for tok in re.split(r"[·()\s,/]+", r.get("ko", "")):
                    add(tok, r["function"])
                if len(key) >= 4:
                    add(key, r["function"])
        for lib, rules in self.generic.items():
            for key, r in rules.items():
                for tok in re.split(r"[·()\s,/]+", r.get("ko", "")):
                    add(tok, r["function"])
        # 같은 낱말이 기능을 둘 이상 가리키면 그대로 둔다(모두 후보)
        _cache["aliases"] = out
        return out

    def question_functions(self, question: str, limit: int = 3) -> list[str]:
        """질문 속 낱말이 가리키는 기능(긴 낱말 우선, 최대 limit 개). 오처리를 줄이는 일반 규칙 셋:
        (1) 한국어 낱말은 앞에 다른 한글이 붙어 있으면 안 된다('색온도'의 '온도'는 안 됨),
        (2) 낱말이 서로 다른 도메인의 기능을 가리키면(예: '컨트롤러') 그 낱말은 쓰지 않는다,
        (3) 맞은 기능들이 둘 이상의 도메인에 걸리면(예: '메모리 카드') 복합 말로 보고 찾지 않는다."""
        q = question.lower()
        by_word: dict[str, set[str]] = {}
        for w, fid in self.aliases():
            by_word.setdefault(w, set()).add(fid)
        score: dict[str, int] = {}
        for w, fids in by_word.items():
            if len({self.funcs[f]["domain"] for f in fids}) > 1:
                continue
            rx = r"(?<![a-z0-9])" + re.escape(w) + r"(?![a-z0-9])" if w.isascii() else r"(?<![가-힣a-z0-9])" + re.escape(w)
            if re.search(rx, q):
                for f in fids:
                    score[f] = max(score.get(f, 0), len(w))
        ranked = [f for f, _ in sorted(score.items(), key=lambda kv: -kv[1])]
        if len({self.funcs[f]["domain"] for f in ranked}) > 1:
            return []
        return ranked[:limit]

    def libraries_for(self, fids) -> set[str]:
        want = set(fids)
        return {lib for lib in list(self.libs) + list(self.generic) if want & set(self.library_functions(lib))}

    def index(self, catalog: list[dict]) -> dict[str, list[dict]]:
        """기능 → 그 기능으로 분류된 부품 목록(카탈로그 전체를 한 번 분류해 둔다)."""
        key = ("index", id(catalog), len(catalog))
        if _cache.get("index_key") != key:
            by: dict[str, list[dict]] = {}
            for p in catalog:
                info = self.classify(p["library"], p["name"], part_text(p))
                if info:
                    by.setdefault(info["function"], []).append(p)
            _cache["index"], _cache["index_key"] = by, key
        return _cache["index"]


def part_text(p: dict) -> str:
    return " ".join(str(p.get(k) or "") for k in ("description", "keywords", "name")).lower()
