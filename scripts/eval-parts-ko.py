#!/usr/bin/env python3
"""한국어 부품 질문 세트(data/eval/parts-ko-questions.jsonl) 시험 — 읽기 전용. ES·LM Studio 필요(질의 임베딩 1건씩).
A 낱말 검색 / B 의미 검색(v2) / C 그래프 전체(분류+검색). 정답은 라이브러리 분류. holdout 은 --holdout 일 때만(기록 남김)."""
from __future__ import annotations
import argparse, json, sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import kicad_parts as kp, ontology_graph as og, parts_graph as pg, rag_search  # noqa: E402

Q = ROOT / "data" / "eval" / "parts-ko-questions.jsonl"
INCLUDE = True
OUT = ROOT / "data" / "eval" / "graph-results"


def is_gold(p, item):
    lib = p.get("library", "")
    return lib in item["gold_libs"] or any(lib.startswith(x) for x in item["gold_prefix"])


def run(part, items, parts, g, es, verbose):
    find_sem = lambda q, n: kp.find_parts(q, parts, n, semantic=True, embed=rag_search.embed_query, es=es)
    vecs = og.load_term_vecs(ROOT / "data" / "ontology" / "term_vecs.npz")
    sem = (lambda q: og.semantic_concepts(g, q, rag_search.embed_query, vecs, include_proposed=INCLUDE)) if vecs else None
    graph = pg.build_parts_graph(pg.PartsDeps(find=find_sem, ontology=g, include_proposed=INCLUDE, semantic_concepts=sem, catalog=parts))
    graph_e = pg.build_parts_graph(pg.PartsDeps(find=find_sem, ontology=g, include_proposed=INCLUDE, semantic_concepts=sem, expand=True, catalog=parts))
    # D: ES·임베딩이 없을 때(낱말 검색 + 온톨로지 영어 키워드 대체)
    graph_d = pg.build_parts_graph(pg.PartsDeps(find=lambda q, n: (kp.search_parts(parts, q, n), "file"),
                                                ontology=g, include_proposed=INCLUDE))
    pos = [i for i in items if i["kind"] == "parts" and i.get("split", part) == part]
    neg = [i for i in items if i["kind"] == "not_parts" and i.get("split", part) == part]
    stat = {"A": [], "B": [], "C": [], "D": [], "E": []}
    handled = 0
    fails = []
    for it in pos:
        for arm, (rows, _) in (("A", (kp.search_parts(parts, it["question"], 5), "file")),
                               ("B", find_sem(it["question"], 5))):
            hits = [is_gold(p, it) for p in rows[:5]]
            stat[arm].append((1 if any(hits) else 0, sum(hits) / 5))
        r = pg.ask_parts(graph, it["question"])
        if r["answered"]:
            handled += 1
            hits = [is_gold(p, it) for p in r["parts"][:5]]
            stat["C"].append((1 if any(hits) else 0, sum(hits) / 5))
            if not any(hits):
                fails.append((it["id"], it["question"], "처리했으나 정답 분류 없음", [p["library"] for p in r["parts"]]))
        else:
            fails.append((it["id"], it["question"], "그래프가 처리하지 못함(분류 통과 못 함)", []))
        re_ = pg.ask_parts(graph_e, it["question"])
        if re_["answered"]:
            hits = [is_gold(p, it) for p in re_["parts"][:5]]
            stat["E"].append((1 if any(hits) else 0, sum(hits) / 5))
        rd = pg.ask_parts(graph_d, it["question"])
        if rd["answered"]:
            hits = [is_gold(p, it) for p in rd["parts"][:5]]
            stat["D"].append((1 if any(hits) else 0, sum(hits) / 5))
    wrong = [i for i in neg if pg.ask_parts(graph, i["question"])["answered"]]
    n = len(pos)
    m = lambda a: sum(x[0] for x in stat[a]) / len(stat[a]) if stat[a] else 0.0
    print(f"== {part} 부품 질문 {n}개 / 부품 아닌 질문 {len(neg)}개 ==")
    print(f"  A 낱말 검색 hit@5 {m('A'):.3f} | B 의미 검색 hit@5 {m('B'):.3f} P@5 {sum(x[1] for x in stat['B'])/n:.3f}")
    print(f"  C 처리율 {handled}/{n} = {handled/n:.3f} | 처리한 것 중 hit@5 {m('C'):.3f} P@5 {(sum(x[1] for x in stat['C'])/len(stat['C'])) if stat['C'] else 0:.3f}")
    print(f"  E(C + 영어 키워드 덧붙임) 처리 {len(stat['E'])}/{n} | 처리한 것 중 hit@5 {m('E'):.3f} P@5 {(sum(x[1] for x in stat['E'])/len(stat['E'])) if stat['E'] else 0:.3f}")
    print(f"  D(ES 없음: 낱말+온톨로지) 처리율 {len(stat['D'])}/{n} | 처리한 것 중 hit@5 {m('D'):.3f}")
    print(f"  부품 아닌 질문을 잘못 처리: {len(wrong)}/{len(neg)}", [i["id"] for i in wrong])
    if verbose:
        for f in fails:
            print("   실패", f[0], f[1], "→", f[2], f[3][:5])
        for i in wrong:
            print("   오처리", i["id"], i["question"])
    return {"A": m("A"), "B": m("B"), "C_cover": handled / n, "C_hit": m("C"), "wrong": len(wrong), "neg": len(neg)}



def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--holdout", action="store_true")
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--label", default="")
    ap.add_argument("--graph", default=str(ROOT / "data" / "ontology" / "graph_ko.json"))
    ap.add_argument("--approved-only", action="store_true", help="승인된 개념만 쓴다(승인 전 개념 제외)")
    ap.add_argument("--as-dev", action="store_true", help="split 이 없는 파일 전체를 dev 로 본다(이미 본 세트에만 쓴다 — holdout 은 열지 않고 기록도 안 남김)")
    ap.add_argument("--file", default=str(Q), help="질문 파일(split 칸이 없으면 전체를 holdout 하나로 본다)")
    args = ap.parse_args()
    qfile = Path(args.file)
    items = [json.loads(l) for l in qfile.read_text(encoding="utf-8").splitlines() if l.strip() and not l.lstrip().startswith("#")]
    if not any("split" in i for i in items):   # 독립 질문 세트: 전체가 새 holdout 한 번
        for i in items:
            i["split"] = "dev" if args.as_dev else "holdout"
    parts, g, es = kp.default_catalog(), og.load_graph(args.graph), rag_search.es_client()
    global INCLUDE
    INCLUDE = not args.approved_only
    if any(i.get("split") == "dev" for i in items):
        run("dev", items, parts, g, es, args.verbose)
    if args.holdout:
        with open(OUT / "holdout-looks.log", "a", encoding="utf-8") as f:
            f.write(f"{datetime.now():%Y-%m-%d %H:%M} parts-ko file={qfile.name} label={args.label}\n")
        run("holdout", items, parts, g, es, args.verbose)


if __name__ == "__main__":
    main()
