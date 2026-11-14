#!/usr/bin/env python3
"""부품 테크트리: 기능 도메인 → DigiKey 분류 경로 → KiCad 라이브러리(부품 수·한국어 개념·대표 부품).

입력: data/digikey/taxonomy_raw.json(뼈대), data/digikey/kicad_mapping_approved.jsonl(라이브러리↔DigiKey, 위임 합의),
      static_data/parts_domains.json(도메인 표), data/ontology/graph_ko.json(승인된 한국어 개념), KiCad 카탈로그.
- 승인(approved) 대응만 '확정', 검토 필요(proposed)는 그 후보 경로에 '검토 필요'로 붙인다. 대응 없음은 '미분류'.
- 도메인 = DigiKey 최상위, IC 는 한 단계 아래(Embedded·Interface…)를 표로 바꾼 것. 표에 없으면 '기타'.
출력: data/parts_tree/tree.json (중첩), data/parts_tree/tree.md (목차)
"""
from __future__ import annotations

import importlib.util
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location("mapdk", ROOT / "scripts" / "map-digikey-kicad.py")
mapdk = importlib.util.module_from_spec(spec); spec.loader.exec_module(mapdk)
OUT = ROOT / "data" / "parts_tree"
IC = "Integrated Circuits (ICs)"


def domain_key(cats, cid):
    path = [cats[i]["name"] for i in mapdk.ancestors(cats, cid)][::-1]
    return path[1] if path[0] == IC and len(path) > 1 else path[0], path


def korean_concepts():
    import ontology_graph as og
    g = og.load_graph(ROOT / "data" / "ontology" / "graph_ko.json")
    ko = defaultdict(list)
    for n, d in g.nodes(data=True):
        if d.get("kind") == "concept" and d.get("review_status") == "approved":
            for nb in g.neighbors(n):
                if g.nodes[nb].get("kind") == "library" and d["label"] not in ko[g.nodes[nb]["label"]]:
                    ko[g.nodes[nb]["label"]].append(d["label"])
    return ko


def main():
    cats = mapdk.categories()
    dom = json.loads((ROOT / "static_data" / "parts_domains.json").read_text(encoding="utf-8"))
    dmap, dinfo = dom["map"], {d["id"]: d for d in dom["domains"]}
    libs, parts = mapdk.kicad_libraries()
    ko = korean_concepts()
    rows = [json.loads(l) for l in (ROOT / "data" / "digikey" / "kicad_mapping_approved.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    tree = {d: {"id": d, "ko": dinfo[d]["ko"], "en": dinfo[d]["en"], "branches": defaultdict(list)} for d in dinfo}
    unmapped = []
    for r in rows:
        lib = r["kicad"]
        leaf = {"kicad": lib, "parts": len(parts.get(lib, [])), "ko_concepts": ko.get(lib, []),
                "examples": [p["name"] for p in parts.get(lib, [])[:3]],
                "status": {"approved": "확정", "proposed": "검토 필요"}.get(r["decision"], "미분류")}
        rules = dom.get("generic_prefix", {}).get(lib)
        if rules:                                   # 일반 분류는 부품 이름 앞부분 규칙으로 쪼갠다
            groups = defaultdict(list)
            keys = sorted((k for k in rules if k not in ("_note", "*")), key=len, reverse=True)
            for p in parts.get(lib, []):
                n = p["name"]
                k = next((k for k in keys if n == k or n.startswith(k + "_")), None)   # 정확히 같거나 '키_' 로 시작(긴 키 먼저)
                hit = rules[k] if k else rules.get("*")
                groups[tuple(hit[:2]) + ((hit[2] if len(hit) > 2 else ""),) if hit else ("other", "(규칙 없음)", "")].append(n)
            for (d, path, kword), names in groups.items():
                tree[d]["branches"][path].append({"kicad": f"{lib} [{path.split(' > ')[-1]}]", "parts": len(names),
                                                  "ko_concepts": [kword] if kword else [],
                                                  "examples": names[:3], "status": "이름 규칙"})
            continue
        if not r.get("digikey_id"):
            unmapped.append(leaf); continue
        key, path = domain_key(cats, r["digikey_id"])
        d = dmap.get(key, "other")
        tree[d]["branches"][" > ".join(path)].append(leaf)
    out = []
    for d in dinfo:
        b = tree[d]["branches"]
        if not b:
            continue
        branches = [{"digikey_path": k, "libraries": sorted(v, key=lambda x: -x["parts"])} for k, v in sorted(b.items())]
        out.append({"id": d, "ko": tree[d]["ko"], "en": tree[d]["en"],
                    "libraries": sum(len(x["libraries"]) for x in branches),
                    "parts": sum(l["parts"] for x in branches for l in x["libraries"]), "branches": branches})
    OUT.mkdir(parents=True, exist_ok=True)
    data = {"domains": out, "unmapped": unmapped,
            "_source": "DigiKey 분류 + KiCad 라이브러리 대응(위임 합의) + 승인 한국어 개념. 검토 전 초안."}
    (OUT / "tree.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    lines = ["# 부품 테크트리 (초안)", ""]
    for d in out:
        lines.append(f"## {d['ko']} — 라이브러리 {d['libraries']}개, 부품 {d['parts']}개")
        for br in d["branches"]:
            lines.append(f"- {br['digikey_path']}")
            for l in br["libraries"]:
                tag = "" if l["status"] == "확정" else f" ({l['status']})"
                kos = f" · {', '.join(l['ko_concepts'][:3])}" if l["ko_concepts"] else ""
                lines.append(f"  - `{l['kicad']}` {l['parts']}개{kos}{tag}")
        lines.append("")
    lines.append(f"## 미분류 — {len(unmapped)}개 (기호 전용·일반 분류)")
    lines.append("- " + ", ".join(f"`{l['kicad']}`" for l in unmapped))
    (OUT / "tree.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    for d in out:
        print(f"{d['ko']}: 라이브러리 {d['libraries']}, 부품 {d['parts']}, 갈래 {len(d['branches'])}")
    print("미분류", len(unmapped))


if __name__ == "__main__":
    main()
