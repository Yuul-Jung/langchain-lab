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
    return re.compile((r"(?<![a-z0-9])" + body + r"(?![a-z0-9])") if ascii_only else body)


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


def translate_query(g: nx.Graph, text: str, include_proposed: bool = False) -> list[str]:
    """질문 속 한국어 용어가 가리키는 개념 노드 목록(긴 용어 우선, 겹치는 용어는 하나만)."""
    terms = sorted((n for n in _nodes(g, "term")), key=lambda n: -len(g.nodes[n]["label"]))
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
            if g.nodes[c].get("review_status") != "approved" and not include_proposed:
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
