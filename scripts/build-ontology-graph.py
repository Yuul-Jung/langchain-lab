#!/usr/bin/env python3
"""KiCad 카탈로그 → 온톨로지 뼈대 그래프(data/ontology/graph.json) 빌드 + 요약 출력.

사용: python scripts/build-ontology-graph.py [--query "ldo regulator"]
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import kicad_parts  # noqa: E402
import ontology_graph as og  # noqa: E402

OUT = ROOT / "data" / "ontology" / "graph.json"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--query", default="", help="질문 확장 시험")
    args = ap.parse_args()
    parts = kicad_parts.default_catalog()
    if not parts:
        print("카탈로그가 비어 있습니다 (data/kicad_catalog/catalog.jsonl).", file=sys.stderr)
        return 1
    g = og.build_graph(parts)
    og.annotate_provenance(g, og.kicad_source(ROOT / "data" / "kicad_catalog" / "SOURCE.json"))
    og.save_graph(g, OUT)
    print(json.dumps(og.summarize(g), ensure_ascii=False, indent=2))
    print(f"저장: {OUT} ({OUT.stat().st_size // 1024} KB)")
    if args.query:
        print("확장:", og.expand_query(g, args.query))
    return 0


if __name__ == "__main__":
    sys.exit(main())
