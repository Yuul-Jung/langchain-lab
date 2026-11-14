#!/usr/bin/env python3
"""부품 질문을 기능 단위로 채점한다 (분류 체계 사용 개선의 판정용, 읽기 전용).

정답: 질문의 gold_functions 가 있으면 상위 5개 부품 중 분류 체계에서 그 기능에 속한 부품이 있을 때 적중.
      gold_regex 가 있으면 gold_libs 안의 부품 이름·설명·키워드(소문자)에 정규식이 맞을 때 적중.
부품의 기능은 분류 체계(static_data/parts_taxonomy.json)에서 구한다: 일반 분류는 이름 규칙, 혼합 분류는 부품 이름 규칙이
있으면 그 기능, 없으면 대표 기능.
설정은 서비스와 같게(승인된 개념만·키워드 덧붙임·여러 조건 설정·학습 관문) 쓴다.
  .venv/bin/python scripts/eval-parts-func.py --file data/eval/parts-ko-questions-71k-func.jsonl [--env PARTS_FUNCTION_RANK=1]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import kicad_parts as kp, ontology_graph as og, parts_gate, parts_graph as pg, parts_taxonomy as pt, rag_search  # noqa: E402
import settings  # noqa: E402

TAX = json.loads((ROOT / "static_data" / "parts_taxonomy.json").read_text(encoding="utf-8"))
LIBS = TAX["libraries"] if isinstance(TAX["libraries"], dict) else dict(TAX["libraries"])
GEN = TAX["generic"]


def function_of(lib: str, name: str):
    if lib in GEN:
        r = pt.match_rule(GEN[lib], name)
        return r["function"] if r else None
    e = LIBS.get(lib)
    if not e:
        return None
    pr = e.get("part_rules")
    if pr:
        r = pt.match_rule(pr, name, "_ ")
        if r and r is not pr.get("*"):
            return r["function"]
    return e["function"]


def is_gold(p: dict, item: dict, text_of) -> bool:
    lib, name = p.get("library", ""), p.get("name", "")
    if item.get("gold_regex"):
        return lib in item.get("gold_libs", []) and re.search(item["gold_regex"], text_of(p)) is not None
    return function_of(lib, name) in item.get("gold_functions", [])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", type=Path, required=True)
    ap.add_argument("--graph", default=None)
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()
    items = [json.loads(l) for l in args.file.read_text(encoding="utf-8").splitlines() if l.strip() and not l.startswith("#")]
    parts, g, es = kp.default_catalog(), og.load_graph(args.graph or ROOT / "data" / "ontology" / "graph_ko.json"), rag_search.es_client()
    full = {p["lib_id"]: p for p in parts}
    text_of = lambda p: " ".join((full.get(p.get("lib_id"), p).get(k) or "") if k != "keywords" else str(full.get(p.get("lib_id"), p).get(k) or "")
                                  for k in ("name", "description", "keywords")).lower()
    find = lambda q, n: kp.find_parts(q, parts, n, semantic=True, embed=rag_search.embed_query, es=es)
    vecs = og.load_term_vecs(ROOT / "data" / "ontology" / "term_vecs.npz")
    sem = (lambda q: og.semantic_concepts(g, q, rag_search.embed_query, vecs, include_proposed=False)) if vecs else None
    kw = dict(find=find, ontology=g, include_proposed=False, semantic_concepts=sem, catalog=parts, expand=True,
              conditions=settings.PARTS_CONDITIONS, bridge=settings.PARTS_BRIDGE,
              veto=(lambda q: parts_gate.veto(q, embed=rag_search.embed_query)) if settings.PARTS_GATE_ML else None)
    graph = pg.build_parts_graph(pg.PartsDeps(**kw))
    pos = [i for i in items if i["kind"] == "parts"]
    neg = [i for i in items if i["kind"] == "not_parts"]
    handled = hits = 0
    fails = []
    for it in pos:
        r = pg.ask_parts(graph, it["question"])
        if r["answered"]:
            handled += 1
            ok = any(is_gold(p, it, text_of) for p in r["parts"][:5])
            hits += ok
            if not ok:
                fails.append((it["id"], it["question"], [function_of(p.get("library", ""), p.get("name", "")) for p in r["parts"][:5]]))
        else:
            fails.append((it["id"], it["question"], "처리 못함"))
    wrong = [i["id"] for i in neg if pg.ask_parts(graph, i["question"])["answered"]]
    print(f"부품 질문 {len(pos)}개: 처리 {handled}/{len(pos)} · 처리한 것 중 상위 5 적중 {hits}/{handled} · 전체 적중 {hits}/{len(pos)}")
    print(f"부품 아닌 질문 {len(neg)}개 중 잘못 처리 {len(wrong)}", wrong)
    if args.verbose:
        for f in fails:
            print("  실패", f)
    return 0


if __name__ == "__main__":
    sys.exit(main())
