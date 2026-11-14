#!/usr/bin/env python3
"""부품 테크트리(화면용): 도메인 → 기능 → KiCad 라이브러리(부품 수·한국어 개념·대표 부품).

입력: static_data/parts_taxonomy.json(우리 분류 체계, scripts/build-parts-taxonomy.py 가 만듦), KiCad 카탈로그, 승인된 한국어 개념.
DigiKey 이름·번호를 쓰지 않는다. 출력(git 제외): data/parts_tree/tree.json, tree.md
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
OUT = ROOT / "data" / "parts_tree"
STATUS_KO = {"confirmed": "확정", "proposed": "검토 필요", "rule": "이름 규칙", "schematic_only": "회로도 전용"}


def match_rule(rules: dict, name: str, seps: str = "_"):
    keys = sorted((k for k in rules if k != "*"), key=len, reverse=True)
    k = next((k for k in keys if name == k or any(name.startswith(k + s) for s in seps)), None)
    return rules.get(k) if k else rules.get("*")


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


def build(tax: dict, parts_by_lib: dict, ko: dict) -> dict:
    funcs = {f["id"]: f for f in tax["functions"]}
    dom = {d["id"]: d for d in tax["domains"]}
    branches = defaultdict(lambda: defaultdict(list))        # 도메인 → 기능 → 잎
    unmapped = []

    def leaf(name, ps, status, concepts, mixed=None):
        d = {"kicad": name, "parts": len(ps), "ko_concepts": concepts, "examples": [p["name"] for p in ps[:3]], "status": STATUS_KO[status]}
        if mixed:
            d["mixed"] = [funcs[x]["ko"] for x in mixed]
        return d
    for lib, e in tax["libraries"].items():
        ps = parts_by_lib.get(lib, [])
        rules = e.get("part_rules") or {}
        rest = []
        split = defaultdict(list)
        for p in ps:     # 부분 이름 규칙에 걸리는 부품은 그 기능의 잎으로 따로 보낸다
            r = match_rule(rules, p["name"], "_-") if rules else None
            (split[r["function"], r.get("ko", "")] if r else rest).append(p)
        for (fid, kword), sub in split.items():
            branches[funcs[fid]["domain"]][fid].append(leaf(f"{lib} [{kword or funcs[fid]['ko']}]", sub, "rule", [kword] if kword else []))
        if rest or not ps:
            branches[funcs[e["function"]]["domain"]][e["function"]].append(
                leaf(lib, rest, e["status"], ko.get(lib, []), e.get("also_functions") if e.get("mixed") else None))
    for lib, rules in tax["generic"].items():
        groups = defaultdict(list)
        for p in parts_by_lib.get(lib, []):
            r = match_rule(rules, p["name"])
            if r:
                groups[(r["function"], r.get("ko", ""))].append(p)
        for (fid, kword), ps in groups.items():
            f = funcs[fid]
            branches[f["domain"]][fid].append(leaf(f"{lib} [{kword or f['ko']}]", ps, "rule", [kword] if kword else []))
    for lib in tax.get("unmapped", []):
        unmapped.append(leaf(lib, parts_by_lib.get(lib, []), "proposed", ko.get(lib, [])) | {"status": "미분류"})
    out = []
    for d in tax["domains"]:
        b = branches.get(d["id"])
        if not b:
            continue
        brs = [{"title": f"{funcs[fid]['ko']} ({funcs[fid]['en']})",
                "libraries": sorted(leaves, key=lambda x: -x["parts"])} for fid, leaves in sorted(b.items(), key=lambda kv: funcs[kv[0]]["ko"])]
        out.append({"id": d["id"], "ko": d["ko"], "en": d["en"], "definition": d.get("definition", ""),
                    "libraries": sum(len(x["libraries"]) for x in brs),
                    "parts": sum(l["parts"] for x in brs for l in x["libraries"]), "branches": brs})
    return {"domains": out, "unmapped": unmapped, "_source": "우리 분류 체계(검토 전 초안): 도메인 → 기능 → KiCad 라이브러리"}


def main():
    import kicad_parts as kp
    tax = json.loads((ROOT / "static_data" / "parts_taxonomy.json").read_text(encoding="utf-8"))
    by_lib = defaultdict(list)
    for p in kp.default_catalog():
        by_lib[p["library"]].append({"name": p["name"]})
    data = build(tax, by_lib, korean_concepts())
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "tree.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    lines = ["# 부품 테크트리 (초안)", ""]
    for d in data["domains"]:
        lines += [f"## {d['ko']} — 라이브러리 {d['libraries']}개, 부품 {d['parts']}개", f"_{d['definition']}_"]
        for b in d["branches"]:
            lines.append(f"- {b['title']}")
            for l in b["libraries"]:
                kos = f" · {', '.join(l['ko_concepts'][:3])}" if l["ko_concepts"] else ""
                lines.append(f"  - `{l['kicad']}` {l['parts']}개{kos} ({l['status']})")
        lines.append("")
    (OUT / "tree.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    for d in data["domains"]:
        print(f"{d['ko']}: 라이브러리 {d['libraries']}, 부품 {d['parts']}, 기능 {len(d['branches'])}")
    print("미분류", len(data["unmapped"]))


if __name__ == "__main__":
    main()
