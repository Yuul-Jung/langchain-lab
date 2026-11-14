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
import parts_taxonomy as pt  # noqa: E402

OUT = ROOT / "data" / "parts_tree"
STATUS_KO = {"confirmed": "확정", "proposed": "검토 필요", "rule": "이름 규칙", "schematic_only": "회로도 전용"}


match_rule = pt.match_rule


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
    """같은 잎(라이브러리 또는 이름 규칙 묶음)으로 기능 보기와 기술 보기를 함께 만든다."""
    funcs = {f["id"]: f for f in tax["functions"]}
    leaves: list[tuple[str, dict]] = []                       # (기능 id, 잎)
    unmapped = []

    def leaf(name, ps, status, concepts, fid, mixed=None):
        d = {"kicad": name, "parts": len(ps), "ko_concepts": concepts, "examples": [p["name"] for p in ps[:3]],
             "status": STATUS_KO[status], "kind": funcs[fid]["kind"]}
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
            leaves.append((fid, leaf(f"{lib} [{kword or funcs[fid]['ko']}]", sub, "rule", [kword] if kword else [], fid)))
        if rest or not ps:
            leaves.append((e["function"], leaf(lib, rest, e["status"], ko.get(lib, []), e["function"],
                                               e.get("also_functions") if e.get("mixed") else None)))
    for lib, rules in tax["generic"].items():
        groups = defaultdict(list)
        for p in parts_by_lib.get(lib, []):
            r = match_rule(rules, p["name"])
            if r:
                groups[(r["function"], r.get("ko", ""))].append(p)
        for (fid, kword), ps in groups.items():
            leaves.append((fid, leaf(f"{lib} [{kword or funcs[fid]['ko']}]", ps, "rule", [kword] if kword else [], fid)))
    for lib in tax.get("unmapped", []):
        unmapped.append(leaf(lib, parts_by_lib.get(lib, []), "proposed", ko.get(lib, []), next(iter(funcs))) | {"status": "미분류", "kind": None})

    def view(group_of, groups_order):
        grouped = defaultdict(lambda: defaultdict(list))      # 묶음 키 → 기능 → 잎
        for fid, lf in leaves:
            grouped[group_of(fid)][fid].append(lf)
        out = []
        for key, info in groups_order:
            fmap = grouped.get(key)
            if not fmap:
                continue
            brs = [{"title": f"{funcs[fid]['ko']} ({funcs[fid]['en']})", "kind": funcs[fid]["kind"],
                    "libraries": sorted(ls, key=lambda x: -x["parts"])} for fid, ls in sorted(fmap.items(), key=lambda kv: funcs[kv[0]]["ko"])]
            out.append({**info, "libraries": sum(len(x["libraries"]) for x in brs),
                        "parts": sum(l["parts"] for x in brs for l in x["libraries"]), "branches": brs})
        return out
    dom = {d["id"]: d for d in tax["domains"]}
    function_view = view(lambda fid: funcs[fid]["domain"],
                         [(d["id"], {"id": d["id"], "ko": d["ko"], "en": d["en"], "definition": d.get("definition", "")}) for d in tax["domains"]])
    tech_keys, seen = [], set()
    for f in tax["functions"]:                                  # 기술 보기 묶음 순서: 반도체 → 비반도체 → 모듈
        g = pt.tech_group(f["kind"], f["domain"])
        if g not in seen:
            seen.add(g); tech_keys.append(g)
    order = {m: i for i, m in enumerate(pt.MATERIAL_KO.values())}
    sub_order = ["IC · " + pt.NATURE_KO[n] for n in ("analog", "power", "digital", "mixed_signal", "unspecified")] + \
                ["개별 소자", "수동 소자", "전기기계", "기구", "회로도 기호", "진공관", "모듈"]
    tech_keys.sort(key=lambda g: (order[g[0]], sub_order.index(g[1]) if g[1] in sub_order else 99))
    tech_view = view(lambda fid: pt.tech_group(funcs[fid]["kind"], funcs[fid]["domain"]),
                     [(g, {"id": f"{g[0]}|{g[1]}", "ko": f"{g[0]} · {g[1]}", "en": "", "definition": ""}) for g in tech_keys])
    return {"domains": function_view, "tech": tech_view, "unmapped": unmapped, "kinds": pt.KIND_KO,
            "_source": "우리 분류 체계(검토 전 초안): 같은 잎으로 만든 기능 보기(domains)와 기술 보기(tech)"}


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
    print("--- 기술 보기")
    for d in data["tech"]:
        print(f"{d['ko']}: 라이브러리 {d['libraries']}, 부품 {d['parts']}")
    print("미분류", len(data["unmapped"]))


if __name__ == "__main__":
    main()
