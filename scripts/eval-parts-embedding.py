#!/usr/bin/env python3
"""한국어 질의 → 영어 부품 설명 임베딩 검색의 가능성을 메모리에서 잰다 (ES 불필요, 읽기 전용).
임베딩은 data/eval/graph-results/parts-embed.npz 에 캐시한다. holdout 은 --holdout 일 때만 본다(기록 남김)."""
from __future__ import annotations
import argparse, hashlib, re, sys
from datetime import datetime
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import kicad_parts, ontology_graph as og, rag_search  # noqa: E402

OUT = ROOT / "data" / "eval" / "graph-results"
CACHE = OUT / "parts-embed.npz"
TOK = re.compile(r"[a-z0-9]+")


def doc_text(p):
    return f"{p.get('name','')}. {p.get('description','')}. {p.get('keywords','')}"[:600]


def load_embeddings(parts):
    ids = [p["lib_id"] for p in parts]
    if CACHE.is_file():
        z = np.load(CACHE, allow_pickle=False)
        if list(z["ids"]) == ids:
            return z["mat"]
    mat = np.zeros((len(parts), 2560), dtype=np.float32)
    for i, p in enumerate(parts):
        v = np.asarray(rag_search.embed_query(doc_text(p)), dtype=np.float32)
        mat[i] = v / (np.linalg.norm(v) or 1)
        if i % 2000 == 0:
            print(f"  임베딩 {i}/{len(parts)}", flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    np.savez(CACHE, ids=np.array(ids), mat=mat)
    return mat


def split_of(term):
    return "dev" if int(hashlib.md5(term.encode()).hexdigest(), 16) % 2 == 0 else "holdout"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--holdout", action="store_true")
    ap.add_argument("--label", default="")
    args = ap.parse_args()
    parts = kicad_parts.default_catalog()
    idx = {p["lib_id"]: i for i, p in enumerate(parts)}
    print("말뭉치", len(parts))
    mat = load_embeddings(parts)
    toks = [set(TOK.findall(doc_text(p).lower())) for p in parts]
    g = og.load_graph(ROOT / "data" / "ontology" / "graph_ko.json")
    cases = []
    for c in [n for n, d in g.nodes(data=True) if d.get("kind") == "concept"]:
        gold = {idx[x["lib_id"]] for x in og.concept_parts(g, c, limit=100000) if x["lib_id"] in idx}
        if 5 <= len(gold) <= 300:
            term = g.nodes[c]["label"]
            cases.append((term, gold))
    print("평가 개념", len(cases), "(정답 5~300개)")
    for part in (["dev", "holdout"] if args.holdout else ["dev"]):
        if part == "holdout":
            with open(OUT / "holdout-looks.log", "a", encoding="utf-8") as f:
                f.write(f"{datetime.now():%Y-%m-%d %H:%M} parts-embedding label={args.label}\n")
        sel = [(t, gd) for t, gd in cases if split_of(t) == part]
        res = {"A": [], "B": []}
        for term, gold in sel:
            for q in (term, f"{term} 부품 추천"):
                qv = np.asarray(rag_search.embed_query(q), dtype=np.float32); qv /= np.linalg.norm(qv) or 1
                top_b = np.argsort(-(mat @ qv))[:5]
                qt = set(TOK.findall(q.lower()))
                sa = np.array([len(qt & t_) for t_ in toks])
                top_a = np.argsort(-sa, kind="stable")[:5] if sa.max() > 0 else []
                for arm, top in (("A", top_a), ("B", top_b)):
                    ranks = [r for r, i in enumerate(top, 1) if i in gold]
                    res[arm].append((1 if ranks else 0, 1 / ranks[0] if ranks else 0, len(ranks) / 5))
        n = len(res["A"])
        print(f"== {part} 개념 {len(sel)} 질의 {n} ==")
        for arm, name in (("A", "낱말 일치"), ("B", "임베딩")):
            r = np.array(res[arm])
            print(f"  {name:8s} hit@5 {r[:,0].mean():.3f}  MRR {r[:,1].mean():.3f}  P@5 {r[:,2].mean():.3f}")


if __name__ == "__main__":
    main()
