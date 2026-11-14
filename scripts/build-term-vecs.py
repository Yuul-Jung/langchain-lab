#!/usr/bin/env python3
"""온톨로지의 한국어 용어(term 노드)를 임베딩해 data/ontology/term_vecs.npz 에 저장한다 (LM Studio 임베딩 사용, 약 400건).
질문 문구가 사전과 정확히 같지 않을 때 가장 가까운 개념을 찾는 보조 단계(ontology_graph.semantic_concepts)가 쓴다."""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import ontology_graph as og, rag_search  # noqa: E402

GRAPH = ROOT / "data" / "ontology" / "graph_ko.json"
OUT = ROOT / "data" / "ontology" / "term_vecs.npz"


def main():
    g = og.load_graph(GRAPH)
    nodes = sorted(n for n, d in g.nodes(data=True) if d.get("kind") == "term")
    mat = np.zeros((len(nodes), 2560), dtype=np.float32)
    for i, n in enumerate(nodes):
        v = np.asarray(rag_search.embed_query(g.nodes[n]["label"]), dtype=np.float32)
        mat[i] = v / (np.linalg.norm(v) or 1)
    np.savez(OUT, nodes=np.array(nodes), mat=mat)
    print(f"용어 {len(nodes)}개 임베딩 → {OUT}")


if __name__ == "__main__":
    main()
