#!/usr/bin/env python3
"""명세 1 질문 세트 채점기(읽기 전용): 서비스와 같은 설정으로 부품 검색 경로를 돌려 칸별로 보고한다.

정답: gold_libs(카탈로그 라이브러리 이름) — 상위 5개 부품 중 하나의 라이브러리가 gold 에 있으면 적중.
      A3(두 부품군)는 gold_libs_pair 의 두 쪽을 각각 상위 5개가 덮으면 '둘 다' 적중(하나만 덮으면 '하나만').
      lib_leak(질문에 정답 라이브러리 이름 낱말이 있음)은 순환 위험이라 기준 계산에서 뺀다(따로 보고).
부품 아닌 질문(kind=not_parts: A4 설명·A5 문서·A6 비부품): 부품 경로가 처리하면 오처리.
사용: .venv/bin/python scripts/eval-parts-spec1.py --file data/eval/spec1/questions-practice.jsonl --rank off|on|service --out data/eval/spec1/result-practice-off.jsonl
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import kicad_parts as kp, ontology_graph as og, parts_gate, parts_graph as pg, parts_taxonomy as pt, rag_search  # noqa: E402
import settings  # noqa: E402


def build(rank: bool, lock: bool = False):
    parts, g, es = kp.default_catalog(), og.load_graph(ROOT / "data" / "ontology" / "graph_ko.json"), rag_search.es_client()
    find = lambda q, n: kp.find_parts(q, parts, n, semantic=True, embed=rag_search.embed_query, es=es)  # noqa: E731
    vecs = og.load_term_vecs(ROOT / "data" / "ontology" / "term_vecs.npz")
    sem = (lambda q: og.semantic_concepts(g, q, rag_search.embed_query, vecs, include_proposed=False)) if vecs else None
    kw = dict(find=find, ontology=g, include_proposed=False, semantic_concepts=sem, catalog=parts, expand=True,
              conditions=settings.PARTS_CONDITIONS, bridge=settings.PARTS_BRIDGE,
              function_rank=rank, taxonomy=(pt.Taxonomy.load() if (rank or lock) else None), anchor_lock=lock,
              veto=(lambda q: parts_gate.veto(q, embed=rag_search.embed_query)) if settings.PARTS_GATE_ML else None)
    return pg.build_parts_graph(pg.PartsDeps(**kw))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", type=Path, required=True)
    ap.add_argument("--rank", choices=["off", "on", "service"], default="service")
    ap.add_argument("--lock", choices=["off", "on", "service"], default="service", help="기준 부품 고정(PARTS_ANCHOR_LOCK)")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--allow-no-embedding", action="store_true", help="임베딩 서버 없이도 측정(결과에 '임베딩 없음'이라고 적어야 함)")
    a = ap.parse_args()
    try:   # 환경 점검: 임베딩 서버 응답
        rag_search.embed_query("환경 점검")
        embed_ok = True
    except Exception as e:  # noqa: BLE001
        embed_ok = False
        print(f"경고: 임베딩 서버 응답 없음({type(e).__name__}) — 의미 검색·임베딩 개념 추측·학습 관문이 동작하지 않는다.", file=sys.stderr)
        if not a.allow_no_embedding:
            print("측정을 중단합니다(--allow-no-embedding 으로 임베딩 없이 측정하면 결과에 '임베딩 없음'을 적어야 함).", file=sys.stderr)
            return 2
    rank = settings.PARTS_FUNCTION_RANK if a.rank == "service" else a.rank == "on"
    items = [json.loads(l) for l in a.file.read_text(encoding="utf-8").splitlines() if l.strip()]
    lock = settings.PARTS_ANCHOR_LOCK if a.lock == "service" else a.lock == "on"
    graph = build(rank, lock)
    res = []
    for it in items:
        r = pg.ask_parts(graph, it["question"])
        libs = [p.get("library", "") for p in (r.get("parts") or [])[:5]] if r["answered"] else []
        rec = {"id": it["id"], "answered": bool(r["answered"]), "top5_libs": libs}
        if r.get("abstain"):
            rec["abstain"] = r["abstain"]
        if r["answered"] and any(p.get("filled") for p in (r.get("parts") or [])[:5]):
            rec["filled"] = [bool(p.get("filled")) for p in (r.get("parts") or [])[:5]]   # 카탈로그 보충으로 채운 자리
        if it["kind"] == "parts":
            gl = set(it["gold_libs"])
            rec["hit"] = bool(r["answered"] and any(l in gl for l in libs))
            if rec["hit"] and rec.get("filled"):   # 검색 결과만으로는 못 맞고 보충 자리로만 맞은 것(정답이 라이브러리 이름이라 따로 센다)
                rec["hit_only_by_fill"] = not any(l in gl for l, f in zip(libs, rec["filled"]) if not f)
            if it.get("gold_libs_pair"):
                cov = [bool(any(l in set(side) for l in libs)) for side in it["gold_libs_pair"]]
                rec["pair_cover"] = cov
        res.append(rec)
    a.out.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in res) + "\n", encoding="utf-8")
    # 요약: 칸별
    by = {it["id"]: it for it in items}
    def rep(name, sel):
        rows = [(by[r["id"]], r) for r in res if sel(by[r["id"]])]
        parts = [(i, r) for i, r in rows if i["kind"] == "parts" and not i.get("lib_leak")]
        notp = [(i, r) for i, r in rows if i["kind"] == "not_parts"]
        out = [f"{name}: 질문 {len(rows)}"]
        if parts:
            h = sum(r["hit"] for _, r in parts); p = sum(r["answered"] for _, r in parts)
            fo = sum(1 for _, r in parts if r.get("hit_only_by_fill")); ab = sum(1 for _, r in parts if r.get("abstain"))
            out.append(f"부품(순환 제외 {len(parts)}): 맞게 답함 {h} · 틀리게 답함 {p - h} · 못 답함 {len(parts) - p}"
                       + (f"(그중 일부러 답하지 않음 {ab})" if ab else "") + (f" · 보충으로만 맞음 {fo}" if fo else ""))
        if notp:
            out.append(f"비부품 {len(notp)}: 오처리 {sum(r['answered'] for _, r in notp)}")
        print(" | ".join(out))
    print(f"설정: rank={'on' if rank else 'off'} lock={'on' if lock else 'off'} 파일 {a.file.name} 질문 {len(items)} · 임베딩 서버 {'응답' if embed_ok else '없음(경고)'}")
    rep("전체", lambda i: True)
    for it_ in ("A1", "A2", "A3", "A4", "A5", "A6"):
        rep(f"의도 {it_}", lambda i, it_=it_: i["intent"] == it_)
    for b in ("B1", "B2", "B3", "B4", "B5"):
        rep(f"틀 {b}", lambda i, b=b: i["frame"] == b)
    rep("C2·C3(부품)", lambda i: i["kind"] == "parts" and i.get("cond", 0) >= 2)
    rep("A6×E4", lambda i: i.get("E") == "E4")
    rep("A2 카탈로그에 있는 부품 이름", lambda i: i["intent"] == "A2" and i.get("pn_in_catalog") is True)
    rep("A2 카탈로그에 없는 부품 이름", lambda i: i["intent"] == "A2" and i.get("pn_in_catalog") is False)
    handled = sum(1 for r in res if r["answered"] and by[r["id"]]["kind"] == "parts")
    total_parts = sum(1 for i in items if i["kind"] == "parts")
    if total_parts and handled / total_parts < 0.5:
        print(f"경고: 부품 질문 처리율이 {handled}/{total_parts} 로 낮다 — 환경(임베딩·ES) 점검 필요")
    leak = sum(1 for i in items if i.get("lib_leak"))
    print(f"순환 위험(lib_leak) {leak}개는 기준 계산에서 제외")
    return 0


if __name__ == "__main__":
    sys.exit(main())
