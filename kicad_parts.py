"""KiCad 부품 목록(심볼 라이브러리)을 읽어 검색하고, 새 부품을 기존 부품에 매핑 제안한다.

원칙
- 부품 정보는 KiCad 공식 라이브러리 안에서만 가져온다 (심볼 파일은 텍스트라 KiCad를 실행하지 않아도 읽힘).
- 매핑은 '제안'만 만든다. 전기적 정격은 라이브러리에 없으므로 비교하지 못했다고 표시하고,
  사람이 승인하기 전에는 쓰지 않는다 (review_status = proposed).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

def _datasheet(props: dict) -> str:
    value = props.get("Datasheet", "")
    return "" if value in ("~", "") else value


def _parse_sexpr(text: str) -> list:
    """S-표현식을 중첩 리스트로 읽는다. 따옴표 문자열(이스케이프 포함)과 원자를 모두 str로 돌려준다.
    형식(KiCad 6·10, 다른 도구가 만든 파일)에 의존하지 않는다. 괄호가 맞지 않으면 ValueError."""
    root: list = []
    stack = [root]
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c in " \t\r\n":
            i += 1
        elif c == "(":
            node: list = []
            stack[-1].append(node)
            stack.append(node)
            i += 1
        elif c == ")":
            if len(stack) == 1:
                raise ValueError("닫는 괄호가 더 많음")
            stack.pop()
            i += 1
        elif c == '"':
            j, buf = i + 1, []
            while j < n and text[j] != '"':
                if text[j] == "\\" and j + 1 < n:
                    j += 1
                buf.append(text[j])
                j += 1
            if j >= n:
                raise ValueError("닫히지 않은 따옴표")
            stack[-1].append("".join(buf))
            i = j + 1
        else:
            j = i
            while j < n and text[j] not in ' \t\r\n()"':
                j += 1
            stack[-1].append(text[i:j])
            i = j
    if len(stack) != 1:
        raise ValueError("닫히지 않은 괄호")
    return root


def _children(node: list, tag: str):
    return [x for x in node if isinstance(x, list) and x and x[0] == tag]


def _collect_pins(node: list, out: list) -> None:
    for x in node:
        if not (isinstance(x, list) and x):
            continue
        if x[0] == "pin" and len(x) > 1:
            nm, num = _children(x, "name"), _children(x, "number")
            if num and len(num[0]) > 1:
                out.append({"number": str(num[0][1]), "name": str(nm[0][1]) if nm and len(nm[0]) > 1 else "",
                            "type": str(x[1])})
        else:
            _collect_pins(x, out)


def parse_symbol_library(text: str, library: str) -> list[dict]:
    """한 .kicad_sym 파일의 최상위 심볼들을 뽑는다. extends는 기본 심볼의 핀·풋프린트로 채운다.

    S-표현식으로 읽으므로 줄바꿈·들여쓰기·속성 표기가 달라도 같은 결과가 나온다.
    kicad_symbol_lib 파일이 아니면 ValueError (조용히 빈 목록을 돌려주지 않는다)."""
    tree = _parse_sexpr(text)
    if not tree or not isinstance(tree[0], list) or not tree[0] or tree[0][0] != "kicad_symbol_lib":
        raise ValueError("kicad_symbol_lib 형식이 아님")
    raw: dict[str, dict] = {}
    order: list[str] = []
    for sym in _children(tree[0], "symbol"):
        if len(sym) < 2:
            continue
        name = str(sym[1])
        props = {str(p[1]): str(p[2]) for p in _children(sym, "property") if len(p) > 2}
        # 하위 단위 심볼(예: NAME_0_1)은 속성이 없으므로 걸러낸다.
        if "Reference" not in props:
            continue
        ext = _children(sym, "extends")
        pins: list = []
        _collect_pins(sym, pins)
        raw[name] = {"library": library, "name": name, "props": props,
                     "extends": str(ext[0][1]) if ext and len(ext[0]) > 1 else "", "pins": pins}
        order.append(name)
    parts = []
    for name in order:
        r = raw[name]
        base = raw.get(r["extends"]) if r["extends"] else None
        pins = r["pins"] or (base["pins"] if base else [])
        props = r["props"]
        footprint = props.get("Footprint", "") or (base["props"].get("Footprint", "") if base else "")
        parts.append({
            "lib_id": f"{library}:{name}",
            "library": library,
            "name": name,
            "description": props.get("Description", "") or (base["props"].get("Description", "") if base else ""),
            "keywords": props.get("ki_keywords", "") or (base["props"].get("ki_keywords", "") if base else ""),
            "footprint": footprint,
            "footprint_filters": props.get("ki_fp_filters", "") or (base["props"].get("ki_fp_filters", "") if base else ""),
            "datasheet": _datasheet(props) or (_datasheet(base["props"]) if base else ""),
            "extends": r["extends"],
            "pin_count": len(pins),
            "pins": pins,
        })
    return parts


def parse_footprint(text: str, library: str, name: str = "") -> dict:
    """한 .kicad_mod 파일을 읽는다. 형식(KiCad 6·10 등)에 의존하지 않는 S-표현식 파서를 쓴다.
    footprint 파일이 아니면 ValueError."""
    tree = _parse_sexpr(text)
    if not tree or not isinstance(tree[0], list) or not tree[0] or tree[0][0] not in ("footprint", "module"):
        raise ValueError("footprint 형식이 아님")
    fp = tree[0]
    fname = name or (str(fp[1]) if len(fp) > 1 and not isinstance(fp[1], list) else "")

    def first(tag):
        c = _children(fp, tag)
        return str(c[0][1]) if c and len(c[0]) > 1 else ""

    pads, models = [], []
    for pad in _children(fp, "pad"):
        if len(pad) > 3:
            pads.append({"number": str(pad[1]), "type": str(pad[2]), "shape": str(pad[3])})
    for m in _children(fp, "model"):
        if len(m) > 1:
            models.append(str(m[1]))
    attrs = [str(x) for a in _children(fp, "attr") for x in a[1:] if not isinstance(x, list)]
    numbers = sorted({p["number"] for p in pads if p["number"] != ""})
    return {"lib_id": f"{library}:{fname}", "library": library, "name": fname,
            "description": first("descr"), "tags": first("tags"), "attr": attrs,
            "pad_count": len(pads), "pad_numbers": numbers, "pads": pads, "models": models}


def load_footprints(footprint_dir: str | Path) -> list[dict]:
    """<폴더>/<라이브러리>.pretty/<이름>.kicad_mod 를 모두 읽는다. 읽지 못한 파일은 목록에 따로 모은다."""
    out, failed = [], []
    for lib in sorted(Path(footprint_dir).glob("*.pretty")):
        for f in sorted(lib.glob("*.kicad_mod")):
            try:
                out.append(parse_footprint(f.read_text(encoding="utf-8", errors="ignore"), lib.name[:-len(".pretty")], f.stem))
            except ValueError as e:
                failed.append({"file": str(f), "error": str(e)})
    load_footprints.failed = failed
    return out


def load_catalog(symbol_dir: str | Path) -> list[dict]:
    parts = []
    for path in sorted(Path(symbol_dir).glob("*.kicad_sym")):
        parts.extend(parse_symbol_library(path.read_text(encoding="utf-8", errors="ignore"), path.stem))
    return parts


def save_catalog(parts: list[dict], path: str | Path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for p in parts:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")


def read_catalog(path: str | Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _tokens(query: str) -> list[str]:
    return [t for t in re.split(r"[\s,;/]+", query.lower()) if t]


def search_parts(parts: list[dict], query: str, limit: int = 10) -> list[dict]:
    """이름·설명·키워드에서 모든 낱말을 포함하는 부품을 점수순으로 돌려준다 (서버 없이 계산)."""
    words = _tokens(query)
    if not words:
        return []
    scored = []
    for p in parts:
        name = p["name"].lower()
        text = f'{p["description"]} {p["keywords"]}'.lower()
        total = 0
        for w in words:
            if name == w:
                s = 6
            elif name.startswith(w):
                s = 4
            elif w in name:
                s = 3
            elif w in text:
                s = 1
            else:
                s = 0
            if s == 0:
                total = 0
                break
            total += s
        if total:
            scored.append((total, p["pin_count"] == 0, p["lib_id"], p))
    scored.sort(key=lambda x: (-x[0], x[1], x[2]))
    return [x[3] for x in scored[:limit]]


def _norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def propose_mapping(source: dict, candidate: dict, footprint: str = "") -> dict:
    """새 부품(source)을 라이브러리 부품(candidate)에 대응시키는 제안을 만든다. 항상 승인 대기 상태.

    source = {"name": ..., "kind": ..., "pins": [{"number": "1", "name": "VCC"}, ...]}
    footprint: 후보 심볼에 풋프린트가 없을 때 호출한 쪽이 지정한 값(누가 정했는지는 제안 파일에 따로 적는다).
    """
    src_pins = source.get("pins", [])
    cand_pins = candidate.get("pins", [])
    by_name = {_norm(p["name"]): p for p in cand_pins if _norm(p["name"])}
    pin_map, matched = [], 0
    for sp in src_pins:
        hit = by_name.get(_norm(sp["name"]))
        if hit:
            matched += 1
            pin_map.append({"source": sp["number"], "target": hit["number"], "by": "name"})
        else:
            pin_map.append({"source": sp["number"], "target": None, "by": "unmatched"})
    # 이름으로 맞는 핀이 없을 때, 핀 수가 같으면 번호 순서 대응을 '약한 근거'로 제안한다.
    positional = False
    if matched == 0 and src_pins and len(src_pins) == len(cand_pins):
        positional = True
        pin_map = [{"source": s["number"], "target": c["number"], "by": "position"}
                   for s, c in zip(src_pins, cand_pins)]
    chosen_fp = footprint or candidate.get("footprint", "")
    checks = {
        "pin_count_match": len(src_pins) == len(cand_pins),
        "pin_name_match_ratio": round(matched / len(src_pins), 2) if src_pins else 0.0,
        "pin_map_basis": "position" if positional else ("name" if matched else "none"),
        "footprint_present": bool(chosen_fp),
        "ratings_compared": False,
    }
    warnings = ["전기적 정격(전압·전류)은 라이브러리에 없어 비교하지 못함 — 데이터시트로 사람이 확인해야 함"]
    if not checks["pin_count_match"]:
        warnings.append("핀 수가 다름")
    if positional:
        warnings.append("핀 이름이 맞지 않아 번호 순서로만 대응함 — 핀 기능이 같은지 반드시 확인")
    if not chosen_fp:
        warnings.append("풋프린트가 정해지지 않음")
    return {
        "source": source,
        "target": {"lib_id": candidate["lib_id"], "footprint": chosen_fp,
                   "footprint_chosen_by": "candidate" if candidate.get("footprint") else ("specified" if footprint else "none")},
        "pin_map": pin_map,
        "checks": checks,
        "warnings": warnings,
        "provenance": "rule_inferred",
        "review_status": "proposed",
    }


def approve_mapping(proposal: dict, reviewer_note: str) -> dict:
    """사람이 승인한 경우에만 호출한다. 근거 없이 승인하면 거절한다."""
    if proposal.get("review_status") != "proposed":
        raise ValueError("승인 대기 상태의 제안만 승인할 수 있습니다.")
    if not reviewer_note.strip():
        raise ValueError("승인 사유를 적어야 합니다.")
    if not proposal["target"]["footprint"]:
        raise ValueError("풋프린트가 정해지지 않은 매핑은 승인할 수 없습니다.")
    if any(m["target"] is None for m in proposal["pin_map"]):
        raise ValueError("대응되지 않은 핀이 있는 매핑은 승인할 수 없습니다.")
    return {**proposal, "review_status": "approved", "reviewer_note": reviewer_note.strip()}


# ---- Elasticsearch (별도 인덱스, 낱말 검색만 사용 — 모델·임베딩 서버가 없어도 동작) ----
ES_PARTS_INDEX = "kicad_parts_v1"


def es_index_body() -> dict:
    return {"settings": {"analysis": {"normalizer": {"lower": {"type": "custom", "filter": ["lowercase"]}}}},
            "mappings": {"properties": {
        "lib_id": {"type": "keyword"}, "library": {"type": "keyword"},
        "name": {"type": "text", "fields": {"raw": {"type": "keyword"},
                                            "lower": {"type": "keyword", "normalizer": "lower"}}},
        "description": {"type": "text"}, "keywords": {"type": "text"},
        "footprint": {"type": "keyword"}, "footprint_filters": {"type": "text"},
        "datasheet": {"type": "keyword"}, "extends": {"type": "keyword"},
        "pin_count": {"type": "integer"},
        "pins": {"type": "object", "enabled": False},
    }}}


def _wildcard_safe(word: str) -> str:
    return re.sub(r"[*?\\]", "", word)


def es_search_body(query: str, limit: int = 10) -> dict | None:
    """모든 낱말이 (설명·키워드의 낱말) 또는 (부품 이름의 일부 문자열)에 있어야 한다."""
    words = [w for w in (_wildcard_safe(t) for t in _tokens(query)) if w]
    if not words:
        return None
    must = [{"bool": {"minimum_should_match": 1, "should": [
        {"multi_match": {"query": w, "fields": ["name^4", "description", "keywords^2"]}},
        {"wildcard": {"name.lower": {"value": f"*{w}*"}}}]}} for w in words]
    return {"size": limit, "query": {"bool": {
        "must": must,
        "should": [{"term": {"name.lower": {"value": w, "boost": 8}}} for w in words]
                  + [{"prefix": {"name.lower": {"value": w, "boost": 3}}} for w in words]}}}


# ---- 의미 검색(v2 인덱스: 임베딩) — 설정 PARTS_SEMANTIC_SEARCH 로 켠다(기본 꺼짐). 실패하면 파일 카탈로그로 대체 ----
ES_PARTS_V2 = "kicad_parts_v2"


def es_semantic_body(vector: list[float], limit: int = 10, num_candidates: int = 200) -> dict:
    return {"size": limit, "_source": {"excludes": ["embedding"]},
            "knn": {"field": "embedding", "query_vector": vector, "k": limit, "num_candidates": num_candidates}}


def find_parts(query: str, parts: list[dict], limit: int = 10, *, semantic: bool = False,
               embed=None, es=None, index: str = ES_PARTS_V2) -> tuple[list[dict], str]:
    """(부품 목록, 쓴 방식). semantic 이 켜져 있고 embed·es 가 있으면 v2 인덱스 의미 검색을 시도하고,
    인덱스가 없거나 서버·임베딩이 실패하거나 결과가 비면 파일 카탈로그 낱말 검색(search_parts)으로 대체한다.
    방식은 'es-semantic' 또는 'file' — 호출한 쪽이 추적(trace)에 남겨 어느 경로로 답했는지 알 수 있게 한다."""
    if semantic and embed is not None and es is not None and query.strip():
        try:
            resp = es.search(index=index, **es_semantic_body(embed(query), limit))
            rows = [h["_source"] for h in resp["hits"]["hits"]]
            if rows:
                return rows, "es-semantic"
        except Exception:
            pass
    return search_parts(parts, query, limit), "file"


def es_bulk_actions(parts: list[dict], index: str = ES_PARTS_INDEX):
    for p in parts:
        yield {"_index": index, "_id": p["lib_id"], "_source": p}


# ---- 채팅에서 부품 핀 질문에 라이브러리 값으로 바로 답하기 (모델을 거치지 않음) ----
CATALOG_PATH = Path(__file__).resolve().parent / "data" / "kicad_catalog" / "catalog.jsonl"
_catalog_cache: dict = {}

_PIN_WORDS = re.compile(r"핀|pin|pinout|핀맵|단자|터미널|terminal|리드선|배선\s*순서", re.I)
_PART_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9\-_.+]*")
_TYPE_KO = {"power_in": "전원 입력", "power_out": "전원 출력", "input": "입력", "output": "출력",
            "bidirectional": "입출력", "passive": "수동", "tri_state": "3상태 출력",
            "open_collector": "오픈 컬렉터", "open_emitter": "오픈 에미터", "unspecified": "미지정",
            "free": "미연결", "no_connect": "연결 안 함", "unconnected": "연결 안 함"}


def default_catalog() -> list[dict]:
    """data/kicad_catalog/catalog.jsonl 을 한 번만 읽는다. 없으면 빈 목록(질문은 모델로 넘어감)."""
    mtime = CATALOG_PATH.stat().st_mtime if CATALOG_PATH.is_file() else None
    # 파일이 없으면 mtime 이 None 이라 처음 호출에서 None != None 이 거짓이 되어 목록을 못 만들던 결함(KeyError)을
    # 고쳤다: 'parts' 가 아직 없으면 항상 만든다 (카탈로그가 없는 새 PC·CI 에서도 빈 목록으로 동작)
    if "parts" not in _catalog_cache or _catalog_cache.get("mtime") != mtime:
        _catalog_cache["parts"] = read_catalog(CATALOG_PATH) if mtime else []
        _catalog_cache["mtime"] = mtime
    return _catalog_cache["parts"]


# ---- 추가 라이브러리(LibrePCB, CC0) : KiCad 에 없는 장치만 덧붙인다 ---------------------------------
# scripts/build-librepcb-catalog.py 가 만든 catalog.jsonl 을 같은 형식으로 바꿔 읽는다. 전부 review_status=proposed
# (커뮤니티 데이터, 사람 승인 전)이므로 핀 답변에 그 사실을 표시한다. 이름이 같은 장치는 KiCad 것만 쓴다(출처가 다른 두 표를
# 섞어 '핀 배치가 서로 다릅니다'로 되묻는 일을 피하고, 공식 라이브러리를 우선).
EXTRA_CATALOG_PATH = Path(__file__).resolve().parent / "data" / "library_staging" / "librepcb" / "catalog.jsonl"
_extra_cache: dict = {}
_ROLE_TO_TYPE = {"passive": "passive", "input": "input", "output": "output", "power": "power_in",
                 "unconnected": "no_connect", "bidirectional": "bidirectional"}


def _extra_part(entry: dict) -> dict:
    return {
        "lib_id": f"LibrePCB/{entry['library']}:{entry['name']}", "library": f"LibrePCB/{entry['library']}",
        "name": entry["name"], "description": entry.get("description", ""),
        "keywords": ",".join(entry.get("keywords", [])), "footprint": entry.get("package", ""),
        "datasheet": (entry.get("datasheets") or [""])[0], "pin_count": entry["pin_count"],
        "pins": [{"number": str(p["number"]), "name": p["name"], "type": _ROLE_TO_TYPE.get(p["role"], p["role"])}
                 for p in entry["pins"]],
        "source": "librepcb", "review_status": entry.get("review_status", "proposed"),
    }


def parts_catalog(include_extras: bool = True) -> list[dict]:
    """KiCad 카탈로그 + (있으면) LibrePCB 추가분. 추가분이 없거나 끄면 KiCad 카탈로그 그대로."""
    base = default_catalog()
    if not include_extras or not EXTRA_CATALOG_PATH.is_file():
        return base
    key = (EXTRA_CATALOG_PATH.stat().st_mtime, id(base), len(base))
    if _extra_cache.get("key") != key:
        have = {_norm(p["name"]) for p in base}
        extras = []
        for line in EXTRA_CATALOG_PATH.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            entry = json.loads(line)
            if entry.get("deprecated") or not entry.get("pin_count") or _norm(entry["name"]) in have:
                continue
            extras.append(_extra_part(entry))
        _extra_cache.update(key=key, parts=base + extras)
    return _extra_cache["parts"]


def _pin_sort_key(pin: dict):
    n = pin["number"]
    return (0, int(n), "") if n.isdigit() else (1, 0, n)


def _pin_label(name: str) -> str:
    m = re.fullmatch(r"~\{(.+)\}", name)
    return f"{m.group(1)} (반전 표기)" if m else name


def _signature(part: dict):
    return tuple((x["number"], x["name"]) for x in sorted(part["pins"], key=_pin_sort_key))


def _candidates(token: str, parts: list[dict]) -> list[dict]:
    """부품 번호 낱말 하나에 해당하는 후보. 정확히 같은 이름 → 이름이 그 낱말로 시작 → (숫자만이면) 이름에 포함."""
    has_pins = [p for p in parts if p["pins"]]
    exact = [p for p in has_pins if p["name"].lower() == token]
    if exact:
        return exact
    starts = [p for p in has_pins if p["name"].lower().startswith(token)]
    if starts:
        return starts
    if token.isdigit():
        return [p for p in has_pins if token in p["name"].lower()]
    return []


PHRASE_MIN_CHARS = 8      # 이름 전체로 찾을 때 영문·숫자만 남긴 이름의 최소 길이


def _phrase_group(question: str, parts: list[dict]) -> list[dict]:
    """질문에 이름 전체가 그대로 있는 부품 (예: 'Arduino Nano V3'). 부품 번호 낱말로는 못 찾는 띄어쓰기 있는 이름용.
    숫자가 든 8자 이상 이름만 보고(일반 낱말과 겹치는 것을 줄임), 가장 긴 이름만 남긴다(짧은 이름이 긴 이름 안에 있는 경우)."""
    nq = _norm(question)
    hits = [(len(n), p) for p in parts if p["pins"]
            for n in [_norm(p["name"])] if len(n) >= PHRASE_MIN_CHARS and re.search(r"\d", n) and n in nq]
    if not hits:
        return []
    longest = max(length for length, _ in hits)
    return [p for length, p in hits if length == longest]


def _candidate_groups(question: str, parts: list[dict]):
    """(질문에 적힌 표기, 후보 부품 목록)을 차례로 돌려준다: 부품 번호 낱말 → (못 찾으면) 이름 전체."""
    found = False
    for token in _PART_TOKEN.findall(question):
        t = token.lower().strip("-_.+")
        if len(t) < 3 or not re.search(r"\d", t):
            continue
        if not t.isdigit() and not re.search(r"[a-z]", t):
            continue
        group = _candidates(t, parts)
        if group:
            found = True
            yield token, group
    if not found:
        group = _phrase_group(question, parts)
        if group:
            yield group[0]["name"], group


def part_tokens(question: str, parts: list[dict]) -> list[str]:
    """핀 질문에서 라이브러리에 있는 부품(질문에 적힌 부품 번호, 또는 이름 전체)을 모두 돌려준다. 핀 질문이 아니거나 없으면 빈 목록.
    parts_answer 와 같은 기준으로 찾는다 (자동 모드가 '문서가 이 부품을 다루는가'를 판단할 때 쓴다)."""
    if not parts or not _PIN_WORDS.search(question):
        return []
    return [label for label, _ in _candidate_groups(question, parts)]


def parts_answer(question: str, parts: list[dict]) -> str | None:
    """핀 질문이고 질문 속 부품 번호(또는 부품 이름 전체)가 라이브러리에 있으면 핀 표를 만들어 돌려준다. 아니면 None.

    후보들의 핀 배치가 서로 다르면 하나를 골라 틀린 표를 주지 않고, 후보를 보여 주며 정확한 번호를 묻는다.
    """
    if not parts or not _PIN_WORDS.search(question):
        return None
    for token, group in _candidate_groups(question, parts):
        group = sorted(group, key=lambda p: (len(p["name"]), p["lib_id"]))
        if len({_signature(p) for p in group}) > 1:
            names = ", ".join(p["lib_id"] for p in group[:8]) + (" 외" if len(group) > 8 else "")
            return (f"`{token}`에 해당하는 부품이 {len(group)}개이고 핀 배치가 서로 다릅니다: {names}\n\n"
                    "틀린 핀 표를 드리지 않도록, 정확한 부품 번호(예: 전체 이름)로 다시 물어봐 주세요.")
        best = group[0]
        pins = sorted(best["pins"], key=_pin_sort_key)
        if best.get("source") == "librepcb":
            head = (f"**{best['name']}** 핀 정보입니다 (LibrePCB 공개 라이브러리 `{best['lib_id']}` 기준, 핀 {best['pin_count']}개). "
                    "**커뮤니티가 만든 데이터이고 사람의 검증·승인 전입니다. 설계에 쓰기 전에 데이터시트로 확인해야 합니다.**")
        else:
            head = f"**{best['name']}** 핀 정보입니다 (KiCad 공식 심볼 라이브러리 `{best['lib_id']}` 기준, 핀 {best['pin_count']}개)."
        lines = [head,
                 "", "| 핀 번호 | 핀 이름 | 전기 유형 |", "|---|---|---|"]
        lines += [f"| {p['number']} | {_pin_label(p['name'])} | {_TYPE_KO.get(p['type'], p['type'])} |" for p in pins]
        notes = []
        if best["footprint"]:
            notes.append(f"기본 풋프린트: `{best['footprint']}`")
        if best["datasheet"]:
            notes.append(f"데이터시트: {best['datasheet']}")
        others = group[1:]
        if others:
            names = ", ".join(p["name"] for p in others[:5]) + (" 외" if len(others) > 5 else "")
            notes.append(f"이름이 같은 계열 부품 {len(others)}개({names})도 있고, 핀 배치는 모두 같습니다.")
        notes.append("전압·전류 같은 전기적 정격과 핀의 기능 설명은 라이브러리에 없으므로 데이터시트로 확인해야 합니다.")
        return "\n".join(lines + [""] + [f"- {n}" for n in notes])
    return None
