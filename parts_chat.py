"""채팅(app.py)이 부품 추천 질문에 쓰는 진입점. 그래프 만들기·온톨로지 읽기·ES 연결을 여기서 하고,
app.py 는 answer(question) 한 줄만 부른다. 켜는 설정은 둘 다 기본 꺼짐:
  PARTS_SEMANTIC_SEARCH=true            부품 의미 검색(ES kicad_parts_v2)을 쓴다
  PARTS_ONTOLOGY_INCLUDE_PROPOSED=true  사람 승인 전(proposed) 한·영 사전도 쓴다 (승인된 개념만 쓰는 것이 원칙, 시험용)
어느 쪽이든 못 쓰면 None 을 돌려주고, 호출한 쪽은 원래 흐름으로 간다."""
from __future__ import annotations

from pathlib import Path

import kicad_parts
import ontology_graph as og
import parts_graph as pg
import settings

GRAPH_PATH = Path(__file__).resolve().parent / "data" / "ontology" / "graph_ko.json"
_cache: dict = {}


def _ontology():
    if not GRAPH_PATH.is_file():
        return None
    mtime = GRAPH_PATH.stat().st_mtime
    if _cache.get("mtime") != mtime:
        _cache["graph"], _cache["mtime"] = og.load_graph(GRAPH_PATH), mtime
    return _cache["graph"]


def answer(question: str, *, es=None, embed=None, ontology=None, catalog=None) -> dict | None:
    """부품 추천 질문이면 {'answer', 'backend', 'trace'}, 아니면 None. 인자는 시험용으로만 바꾼다."""
    if not settings.PARTS_SEMANTIC_SEARCH:
        return None
    onto = ontology if ontology is not None else _ontology()
    if onto is None:
        return None
    if es is None or embed is None:
        try:
            import rag_search
            es, embed = es or rag_search.es_client(), embed or rag_search.embed_query
        except Exception:
            es = embed = None
    parts = catalog if catalog is not None else kicad_parts.default_catalog()
    deps = pg.PartsDeps(
        find=lambda q, n: kicad_parts.find_parts(q, parts, n, semantic=True, embed=embed, es=es),
        ontology=onto, include_proposed=settings.PARTS_ONTOLOGY_INCLUDE_PROPOSED)
    result = pg.ask_parts(pg.build_parts_graph(deps), question)
    if not result.get("answered"):
        return None
    return {"answer": result["answer"], "backend": result["backend"], "trace": result["trace"]}
