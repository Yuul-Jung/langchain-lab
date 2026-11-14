"""KiCad 부품 카탈로그에서 온톨로지 뼈대(개념·관계 그래프)를 자동으로 뽑는다.

작업일지 '방향 재정렬' 3번 — 라이브러리 위에 개념·관계를 얹는다.
- 클래스 후보: 라이브러리(분류) 노드
- 개념·동의어 후보: 키워드 노드 (같은 부품에 같이 붙는 키워드는 related 간선)
- 부품 노드: 설명·핀 수·데이터시트 보유 여부
- 풋프린트 노드: 부품이 연결한 풋프린트
- 모든 개념 후보는 review_status = proposed (사람이 승인해야 쓴다)

이 모듈은 순수 함수만 둔다. 채팅(app.py)과 연결하지 않는다.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from itertools import combinations
from pathlib import Path

import networkx as nx

# 한 부품에 키워드가 너무 많으면 쌍이 폭증하므로 상한을 둔다.
MAX_KEYWORDS_PER_PART = 8
# 이 횟수 미만으로 같이 나온 키워드 쌍은 우연으로 보고 버린다.
MIN_COOCCURRENCE = 3

_TOKEN = re.compile(r"[^\s,;]+")


def split_keywords(raw: str) -> list[str]:
    """ki_keywords 문자열을 소문자 키워드 목록으로 (중복 제거, 순서 유지)."""
    seen: dict[str, None] = {}
    for tok in _TOKEN.findall(raw or ""):
        tok = tok.strip().lower()
        if len(tok) >= 2:
            seen.setdefault(tok, None)
    return list(seen)


def build_graph(parts: list[dict], min_cooccurrence: int = MIN_COOCCURRENCE) -> nx.Graph:
    """부품 목록 → 무방향 그래프. 노드 kind: library / part / keyword / footprint."""
    g = nx.Graph()
    pair_counts: Counter = Counter()
    for p in parts:
        lib, pid = p.get("library", ""), p.get("lib_id", "")
        if not lib or not pid:
            continue
        lib_node, part_node = f"lib:{lib}", f"part:{pid}"
        g.add_node(lib_node, kind="library", label=lib, review_status="proposed")
        g.add_node(part_node, kind="part", label=p.get("name", ""),
                   description=p.get("description", ""), pin_count=p.get("pin_count", 0),
                   has_datasheet=bool(p.get("datasheet")))
        g.add_edge(part_node, lib_node, relation="in_library")
        if p.get("extends"):
            g.add_edge(part_node, f"part:{lib}:{p['extends']}", relation="extends")
        if p.get("footprint"):
            fp = f"fp:{p['footprint']}"
            g.add_node(fp, kind="footprint", label=p["footprint"])
            g.add_edge(part_node, fp, relation="uses_footprint")
        kws = split_keywords(p.get("keywords", ""))[:MAX_KEYWORDS_PER_PART]
        for kw in kws:
            kw_node = f"kw:{kw}"
            g.add_node(kw_node, kind="keyword", label=kw, review_status="proposed")
            g.add_edge(part_node, kw_node, relation="has_keyword")
        pair_counts.update(combinations(sorted(kws), 2))
    for (a, b), n in pair_counts.items():
        if n >= min_cooccurrence:
            g.add_edge(f"kw:{a}", f"kw:{b}", relation="related", weight=n)
    # extends가 가리키는 기본 심볼이 카탈로그에 없으면 kind가 없는 빈 노드가 생긴다 → 제거
    g.remove_nodes_from([n for n, d in list(g.nodes(data=True)) if "kind" not in d])
    return g


def _nodes(g: nx.Graph, kind: str):
    return [n for n, d in g.nodes(data=True) if d.get("kind") == kind]


def summarize(g: nx.Graph) -> dict:
    """그래프 요약 (빌드 스크립트·시험 출력용)."""
    kinds = Counter(d.get("kind") for _, d in g.nodes(data=True))
    kw_deg = sorted(((g.degree(n), g.nodes[n]["label"]) for n in _nodes(g, "keyword")), reverse=True)
    return {
        "nodes": g.number_of_nodes(), "edges": g.number_of_edges(), "kinds": dict(kinds),
        "top_keywords": [{"keyword": k, "degree": d} for d, k in kw_deg[:15]],
    }


def related_concepts(g: nx.Graph, keyword: str, limit: int = 10) -> list[dict]:
    """키워드와 같이 자주 나오는 키워드(동의어·인접 개념 후보), 많이 같이 나온 순."""
    node = f"kw:{keyword.lower()}"
    if node not in g:
        return []
    out = [(g.edges[node, n]["weight"], g.nodes[n]["label"]) for n in g.neighbors(node)
           if g.edges[node, n].get("relation") == "related"]
    out.sort(key=lambda x: (-x[0], x[1]))
    return [{"keyword": k, "cooccurrence": w} for w, k in out[:limit]]


def parts_for_concept(g: nx.Graph, keyword: str, limit: int = 10) -> list[dict]:
    """키워드가 붙은 부품 목록 (데이터시트 있는 부품, 핀 많은 부품 순)."""
    node = f"kw:{keyword.lower()}"
    if node not in g:
        return []
    parts = [(n, g.nodes[n]) for n in g.neighbors(node) if g.nodes[n].get("kind") == "part"]
    parts.sort(key=lambda x: (not x[1].get("has_datasheet"), -x[1].get("pin_count", 0), x[0]))
    return [{"lib_id": n[len("part:"):], "description": d.get("description", ""),
             "pin_count": d.get("pin_count", 0)} for n, d in parts[:limit]]


def expand_query(g: nx.Graph, text: str, per_term: int = 3) -> list[str]:
    """질문 속 단어 중 그래프의 개념과 일치하는 것을 찾고, 그 인접 개념을 덧붙여 돌려준다.
    일치하는 개념이 없으면 빈 목록 (검색을 바꾸지 않는다)."""
    terms = split_keywords(text)
    hits = [t for t in terms if f"kw:{t}" in g]
    extra: list[str] = []
    for t in hits:
        for r in related_concepts(g, t, per_term):
            if r["keyword"] not in terms and r["keyword"] not in extra:
                extra.append(r["keyword"])
    return extra


def library_profile(g: nx.Graph, library: str, limit: int = 10) -> list[dict]:
    """라이브러리(분류)를 대표하는 키워드: 그 라이브러리 부품에 많이 붙은 순."""
    node = f"lib:{library}"
    if node not in g:
        return []
    cnt: Counter = Counter()
    for part in g.neighbors(node):
        for n in g.neighbors(part):
            if g.nodes[n].get("kind") == "keyword":
                cnt[g.nodes[n]["label"]] += 1
    return [{"keyword": k, "parts": c} for k, c in cnt.most_common(limit)]


# ---- 출처(provenance): 그래프 전체와 노드마다 "어디서 왔고 근거가 몇 개인가" -------------------------------
def readable_name(library: str) -> str:
    """라이브러리 이름을 사람이 읽을 영어 이름 후보로 (Regulator_Linear → 'Regulator Linear'). 번역이 아니라 표기 정리."""
    return re.sub(r"\s+", " ", library.replace("_", " ")).strip()


def kicad_source(path: str | Path) -> dict:
    """data/kicad_catalog/SOURCE.json 에서 받은 날짜·커밋·라이선스를 뽑는다. 파일이 없으면 빈 사전(그래프는 출처 없이 만들어진다)."""
    p = Path(path)
    if not p.is_file():
        return {}
    raw = json.loads(p.read_text(encoding="utf-8"))
    ext = raw.get("extensions", {})
    return {"catalog": "KiCad official libraries", "fetched": raw.get("fetched"), "license": raw.get("license"),
            "symbols_commit": (ext.get("symbols") or {}).get("Commit"),
            "footprints_commit": (ext.get("footprints") or {}).get("Commit")}


def _example_parts(g: nx.Graph, part_nodes: list[str], k: int) -> list[str]:
    rows = sorted(((not g.nodes[n].get("has_datasheet"), -g.nodes[n].get("pin_count", 0), n) for n in part_nodes))
    return [n[len("part:"):] for _, _, n in rows[:k]]


def annotate_provenance(g: nx.Graph, source: dict | None = None, examples: int = 3) -> None:
    """그래프 전체에 출처(g.graph['source'])를, 라이브러리·키워드·개념 노드마다 근거 부품 수(evidence_parts)와
    예시 부품 lib_id(example_parts)를 붙인다. 라이브러리에는 읽을 이름 후보(display_name_en)·대표 키워드·
    (한·영 다리가 있으면) 한국어 이름 후보(ko_names)도 붙인다. 모두 후보이며 사람이 승인해야 쓴다."""
    if source:
        g.graph["source"] = source
    for n, d in list(g.nodes(data=True)):
        kind = d.get("kind")
        if kind in ("library", "keyword"):
            parts = [m for m in g.neighbors(n) if g.nodes[m].get("kind") == "part"]
            d["evidence_parts"] = len(parts)
            d["example_parts"] = _example_parts(g, parts, examples)
            d["origin"] = "catalog"
            if kind == "library":
                d["display_name_en"] = readable_name(d["label"])
                d["top_keywords"] = [x["keyword"] for x in library_profile(g, d["label"], 5)]
                d["ko_names"] = sorted(g.nodes[c]["label"] for c in g.neighbors(n) if g.nodes[c].get("kind") == "concept")
        elif kind == "concept":
            rows = concept_parts(g, n, limit=10 ** 6)
            d["evidence_parts"] = len(rows)
            d["example_parts"] = [r["lib_id"] for r in rows[:examples]]
            d["origin"] = "claude-authored seed (static_data/ontology_ko_en_seed.json), 사람 승인 전"


def save_graph(g: nx.Graph, path: str | Path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(nx.node_link_data(g, edges="edges"), ensure_ascii=False), encoding="utf-8")


def load_graph(path: str | Path) -> nx.Graph:
    return nx.node_link_graph(json.loads(Path(path).read_text(encoding="utf-8")), edges="edges")


# ---- 한·영 다리: 한국어 용어 → 개념 → 카탈로그 키워드·분류 -----------------------------------------
# 모든 개념은 review_status 를 가진다. 기본은 proposed 이고, 사람이 approved 로 바꾸기 전에는
# translate_query/ask_ko 가 쓰지 않는다 (include_proposed=True 로 시험할 때만 보인다).
import functools

_SEP = r"[\s\-_/]*"


@functools.lru_cache(maxsize=2048)
def _term_regex(term: str):
    chars = [re.escape(c) for c in term.lower() if not c.isspace() and c not in "-_/"]
    ascii_only = all(ord(c) < 128 for c in term)
    body = _SEP.join(chars)
    # 영문·숫자만인 용어는 다른 낱말 속에서 찾아지지 않게(예: 'led' 가 'called' 에서) 경계를 둔다
    if ascii_only:
        return re.compile(r"(?<![a-z0-9])" + body + r"(?![a-z0-9])")
    # 한 글자 한국어 용어(램·롬)는 다른 낱말 속에서 걸리지 않게(예: '프로그램' 의 '램'): 앞이 한글이면 안 되고,
    # 뒤는 한글이 아니거나 조사(을·를·은·는·이·가·도·과·와·의·에·로·으로) 뒤가 끝나야 한다
    if len(chars) == 1:
        return re.compile(r"(?<![가-힣])" + body + r"(?:(?![가-힣])|(?=(?:으로|[을를은는이가도과와의에로])(?![가-힣])))")
    return re.compile(body)


def add_korean_bridge(g: nx.Graph, entries: list[dict]) -> int:
    """entries([{'ko': [...], 'kw': [...], 'lib': [...], 'lib_prefix': [...], 'review_status': ...}]) 를 그래프에 얹는다.
    개념 노드 하나가 한국어 용어 노드들과 카탈로그 키워드·분류 노드를 잇는다. 카탈로그에 없는 연결 대상은 만들지 않고
    누락 목록으로 돌려준다. 돌려주는 값: 만든 개념 수."""
    libs = {g.nodes[n]["label"]: n for n in _nodes(g, "library")}
    made = 0
    for i, e in enumerate(entries):
        concept = f"concept:{i}"
        status = e.get("review_status", "proposed")
        g.add_node(concept, kind="concept", label=e["ko"][0], review_status=status)
        for term in e["ko"]:
            tn = f"term:{term.lower()}"
            g.add_node(tn, kind="term", label=term)
            g.add_edge(tn, concept, relation="term_of")
        for kw in e.get("kw", []):
            if f"kw:{kw}" in g:
                g.add_edge(concept, f"kw:{kw}", relation="means_keyword")
        for name in e.get("lib", []):
            if name in libs:
                g.add_edge(concept, libs[name], relation="means_class")
        for prefix in e.get("lib_prefix", []):
            for name, node in libs.items():
                if name.startswith(prefix):
                    g.add_edge(concept, node, relation="means_class")
        made += 1
    return made


def translate_query(g: nx.Graph, text: str, include_proposed: bool = False, skip_risky: bool = False) -> list[str]:
    """질문 속 한국어 용어가 가리키는 개념 노드 목록(긴 용어 우선, 겹치는 용어는 하나만).
    skip_risky=True 면 오탐 위험 표시(risky)가 붙은 용어는 쓰지 않는다(의도어 없는 짧은 질문 경로용)."""
    terms = sorted((n for n in _nodes(g, "term") if not (skip_risky and g.nodes[n].get("risky"))),
                   key=lambda n: -len(g.nodes[n]["label"]))
    lowered = text.lower()
    taken: list[tuple[int, int]] = []
    concepts: list[str] = []
    for tn in terms:
        m = _term_regex(g.nodes[tn]["label"]).search(lowered)
        if not m or any(m.start() < b and a < m.end() for a, b in taken):
            continue
        for c in g.neighbors(tn):
            if g.nodes[c].get("kind") != "concept":
                continue
            status = g.nodes[c].get("review_status")
            if status == "rejected" or (status != "approved" and not include_proposed):   # 반려된 개념은 어떤 설정에서도 쓰지 않는다
                continue
            taken.append((m.start(), m.end()))
            if c not in concepts:
                concepts.append(c)
    return concepts


def concept_parts(g: nx.Graph, concept: str, limit: int = 10) -> list[dict]:
    """개념의 카탈로그 부품: 개념이 가리키는 키워드를 모두 가진 부품(있다면) 중 개념의 분류 안에 있는 것."""
    kws = [n for n in g.neighbors(concept) if g.nodes[n].get("kind") == "keyword"]
    libs = [n for n in g.neighbors(concept) if g.nodes[n].get("kind") == "library"]
    pool: set[str] | None = None
    for lib in libs:
        pool = (pool or set()) | {n for n in g.neighbors(lib) if g.nodes[n].get("kind") == "part"}
    for kw in kws:
        have = {n for n in g.neighbors(kw) if g.nodes[n].get("kind") == "part"}
        pool = have if pool is None else pool & have
    if not pool:
        return []
    rows = [(n, g.nodes[n]) for n in pool]
    rows.sort(key=lambda x: (not x[1].get("has_datasheet"), -x[1].get("pin_count", 0), x[0]))
    return [{"lib_id": n[len("part:"):], "description": d.get("description", ""), "pin_count": d.get("pin_count", 0)}
            for n, d in rows[:limit]]


def ask_ko(g: nx.Graph, text: str, include_proposed: bool = False, limit: int = 5) -> list[dict]:
    """한국어 질문 → [{'concept': 개념 이름, 'status': 승인 상태, 'parts': [...]}]. 이해한 개념이 없으면 빈 목록."""
    out = []
    for c in translate_query(g, text, include_proposed):
        out.append({"concept": g.nodes[c]["label"], "status": g.nodes[c].get("review_status"),
                    "parts": concept_parts(g, c, limit)})
    return out


def semantic_concepts(g: nx.Graph, text: str, embed, term_vecs: dict, threshold: float = 0.75,
                      include_proposed: bool = False, limit: int = 2) -> list[str]:
    """질문이 사전의 용어와 문구만 다르고 뜻이 아주 가까울 때(예: '절연된' ↔ '절연형') 그 개념을 찾는다.
    term_vecs = {'nodes': [term 노드 id...], 'mat': (n, d) 단위 벡터 행렬}. 문턱 미만이면 찾지 않는다(비어 있음).
    임베딩이 안 되면(서버 없음) 빈 목록. 문턱 0.75 는 dev 에서 정함: 부품 아닌 질문이 관문을 통과했을 때의 최고 0.64 와
    표현 변형 0.78~0.79 사이의 보수적인 값이다."""
    import numpy as np
    try:   # 서버가 없거나 벡터 크기가 맞지 않으면 보조 단계만 건너뛴다(질문 처리를 깨지 않는다)
        v = np.asarray(embed(text), dtype=np.float32)
        v = v / (np.linalg.norm(v) or 1)
        sims = term_vecs["mat"] @ v
    except Exception:
        return []
    out: list[str] = []
    for j in np.argsort(-sims)[:6]:
        if sims[j] < threshold:
            break
        if g.nodes.get(term_vecs["nodes"][j], {}).get("risky"):   # 오탐 위험 용어는 문구가 비슷하다는 이유만으로 잇지 않는다
            continue
        for c in g.neighbors(term_vecs["nodes"][j]):
            if g.nodes[c].get("kind") != "concept" or c in out:
                continue
            status = g.nodes[c].get("review_status")
            if status == "rejected" or (status != "approved" and not include_proposed):
                continue
            out.append(c)
    return out[:limit]


def load_term_vecs(path: str | Path) -> dict | None:
    """scripts/build-term-vecs.py 가 만든 용어 임베딩. 파일이 없으면 None(보조 단계를 쓰지 않는다)."""
    p = Path(path)
    if not p.is_file():
        return None
    import numpy as np
    z = np.load(p, allow_pickle=False)
    return {"nodes": [str(n) for n in z["nodes"]], "mat": z["mat"]}


def attach_wikidata(g: nx.Graph, rows: list[dict]) -> dict:
    """Wikidata 대조 결과(동료 K2: data/ontology/ko_wikidata.jsonl)를 '근거 보조'로만 붙인다. **승인(review_status)은 바꾸지 않는다.**
    ko->en 행만 본다. 용어 노드에: wikidata_qid·wikidata_url·wikidata_label_en·wikidata_support
    (support = 'electronics_match'(영어와 맞고 전기·전자 분야) | 'other_domain'(맞지만 분야 다름) | 'mismatch'(어긋남)).
    개념 노드에는 전기·전자 분야로 확인된 용어 수(wikidata_supported_terms)와 qid 목록을 붙인다. 못 찾은 용어는 아무것도 붙이지 않는다.
    돌려주는 값: 상태별 개수."""
    counts = {"electronics_match": 0, "other_domain": 0, "mismatch": 0}
    for r in rows:
        if r.get("direction", "ko->en") != "ko->en" or r.get("verdict") not in ("match", "mismatch") or not r.get("qid"):
            continue
        node = f"term:{r['term'].lower()}"
        if node not in g:
            continue
        if r["verdict"] == "mismatch":
            support = "mismatch"
        else:
            support = "electronics_match" if r.get("domain") == "electronics" else "other_domain"
        d = g.nodes[node]
        d.update(wikidata_qid=r["qid"], wikidata_url=r.get("url"), wikidata_label_en=r.get("en_label"), wikidata_support=support)
        counts[support] += 1
    for c, d in g.nodes(data=True):
        if d.get("kind") != "concept":
            continue
        qids = [g.nodes[t]["wikidata_qid"] for t in g.neighbors(c)
                if g.nodes[t].get("wikidata_support") == "electronics_match"]
        if qids:
            d["wikidata_supported_terms"] = len(qids)
            d["wikidata_qids"] = sorted(set(qids))
            d["wikidata_note"] = "Wikidata(CC0) 근거 보조 — 승인 대용이 아님, 사람 승인 필요"
    return counts


def apply_approvals(g: nx.Graph, rows: list[dict]) -> dict:
    """승인 기록(data/ontology/approvals.jsonl)을 개념 노드에 반영한다. 시드 파일은 바꾸지 않는다.
    한 줄: {'index': 개념 번호, 'ko': 대표 한국어 용어(번호와 짝이 맞는지 확인용), 'decision': approved|rejected|proposed,
            'approver': 누가(예: 'delegated: jung-29 + 71 (사용자 위임)'), 'date': 날짜, 'reason': 이유}
    같은 개념이 여러 줄이면 마지막 줄이 이긴다. 번호와 대표 용어가 안 맞으면(시드 순서가 바뀐 경우) 반영하지 않고 세어 돌려준다."""
    counts = {"approved": 0, "rejected": 0, "proposed": 0, "mismatch": 0}
    for r in rows:
        if "decision" not in r:   # 머리말 줄(_note) 등은 건너뛴다
            continue
        c = f"concept:{r.get('index')}"
        decision = r.get("decision")
        if c not in g or decision not in ("approved", "rejected", "proposed"):
            counts["mismatch"] += 1
            continue
        if g.nodes[c].get("label") != r.get("ko"):
            counts["mismatch"] += 1
            continue
        g.nodes[c].update(review_status=decision, review_by=r.get("approver"), review_at=r.get("date"),
                          review_note=r.get("reason", ""))
        for term in r.get("risky_terms", []):   # 개념 승인과 별개로, 그 용어는 의도어가 있을 때만 쓰게 표시
            tn = f"term:{term.lower()}"
            if tn in g:
                g.nodes[tn]["risky"] = True
    final = [d.get("review_status") for _, d in g.nodes(data=True) if d.get("kind") == "concept"]
    counts.update({k: final.count(k) for k in ("approved", "rejected", "proposed")})
    return counts

