#!/usr/bin/env python3
"""한·영 용어 후보 사전(static_data/ontology_ko_en_seed.json)을 카탈로그 온톨로지 그래프에 얹어 저장한다.

- 입력: data/kicad_catalog (카탈로그), static_data/ontology_ko_en_seed.json (후보, 전부 proposed)
- 출력: data/ontology/graph_ko.json (기존 graph.json 은 건드리지 않음)
- 검증: 각 후보가 카탈로그의 키워드·분류에 실제로 연결되는지, 연결된 부품이 몇 개인지 보고한다.
사용: python scripts/build-ontology-ko.py [--ask "저전압 강하 레귤레이터 찾아줘"]
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import kicad_parts  # noqa: E402
import ontology_graph as og  # noqa: E402

SEED = ROOT / "static_data" / "ontology_ko_en_seed.json"
OUT = ROOT / "data" / "ontology" / "graph_ko.json"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ask", default="")
    args = ap.parse_args()
    entries = json.loads(SEED.read_text(encoding="utf-8"))["entries"]
    g = og.build_graph(kicad_parts.default_catalog())
    og.add_korean_bridge(g, entries)
    og.annotate_provenance(g, og.kicad_source(ROOT / "data" / "kicad_catalog" / "SOURCE.json"))
    og.save_graph(g, OUT)
    empty, linked = [], 0
    for n, d in g.nodes(data=True):
        if d.get("kind") != "concept":
            continue
        parts = og.concept_parts(g, n, limit=10**6)
        linked += bool(parts)
        if not parts:
            empty.append(d["label"])
    total = sum(1 for _, d in g.nodes(data=True) if d.get("kind") == "concept")
    print(f"개념 {total}개 · 용어 {sum(1 for _, d in g.nodes(data=True) if d.get('kind') == 'term')}개 · "
          f"부품에 닿는 개념 {linked}개 · 부품이 없는 개념 {len(empty)}개 {empty}")
    print("저장:", OUT)
    if args.ask:
        for r in og.ask_ko(g, args.ask, include_proposed=True):
            print(f"- {r['concept']} [{r['status']}]", [p["lib_id"] for p in r["parts"]])
    return 0


if __name__ == "__main__":
    sys.exit(main())
