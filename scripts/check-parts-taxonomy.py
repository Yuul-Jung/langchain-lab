#!/usr/bin/env python3
"""부품 분류 체계 검사기(결정적). 실행 전에 정한 검사 4가지 + 구조 검사.

1) KiCad 라이브러리가 모두 정확히 한 번 나온다(분류·일반 분류·회로도 전용·미분류 중 하나). 모르는 라이브러리·중복·빠진 라이브러리는 실패.
   일반 분류(Device 등)는 부품 이름이 규칙에 모두 걸려야 한다.
2) 라이브러리마다 기능이 정확히 하나이고, 기능은 도메인 하나에 속한다. 둘 이상에 걸리는 경우는 also_ok(다른 도메인 id)로만 적는다.
   '확정(confirmed)'에는 확인자 표시가 있어야 한다('delegated:' 또는 'human:'로 시작) — 두 단계 검토 없이는 확정이 없다.
3) 참고 파일(data/parts_tree/digikey_ref.json)이 있고 DigiKey 분류 원본(data/digikey/taxonomy_raw.json)도 있으면, 쓴 DigiKey 번호가 모두 있어야 한다.
   둘 중 하나가 없으면 이 검사는 건너뛴다(없는 컴퓨터에서도 실패하지 않는다).
4) 적용 범위: 전체 부품 중 확정·이름 규칙·검토 필요·회로도 전용·미분류 비율(실패 조건 아님, 숫자 보고).
종료 코드: 1~3 중 하나라도 실패하면 1.
사용: .venv/bin/python scripts/check-parts-taxonomy.py [--json]
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TAXONOMY = ROOT / "static_data" / "parts_taxonomy.json"
REF = ROOT / "data" / "parts_tree" / "digikey_ref.json"
RAW = ROOT / "data" / "digikey" / "taxonomy_raw.json"
STATUSES = {"confirmed", "proposed", "rule", "schematic_only"}


def match_rule(rules: dict, name: str, seps: str = "_"):
    """이름이 키와 같거나 '키+구분자'로 시작하면 그 규칙(긴 키 먼저). 'R' 이 'RotaryEncoder' 를 삼키지 않는다."""
    keys = sorted((k for k in rules if k != "*"), key=len, reverse=True)
    k = next((k for k in keys if name == k or any(name.startswith(k + s) for s in seps)), None)
    return rules.get(k) if k else rules.get("*")


def validate(tax: dict, parts: list[dict], ref: dict | None = None, digikey_ids: set | None = None) -> dict:
    """tax: parts_taxonomy.json 내용, parts: [{'library','name'}...]. 문제 목록과 적용 범위를 돌려준다."""
    problems: dict[str, list] = {"check1": [], "check2": [], "check3": []}
    domains = {d["id"] for d in tax["domains"]}
    funcs = {f["id"]: f for f in tax["functions"]}
    if len(domains) != len(tax["domains"]):
        problems["check2"].append("도메인 id 중복")
    for d in tax["domains"]:
        if not d.get("definition"):
            problems["check2"].append(f"도메인 정의 없음: {d['id']}")
    for fid, f in funcs.items():
        if f["domain"] not in domains:
            problems["check2"].append(f"기능 {fid} 의 도메인 {f['domain']} 이 없음")
    libs, generic, unmapped = tax["libraries"], tax["generic"], set(tax.get("unmapped", []))
    # --- 검사 1: 라이브러리마다 정확히 한 곳
    homes = Counter()
    for lib in libs: homes[lib] += 1
    for lib in generic: homes[lib] += 1
    for lib in unmapped: homes[lib] += 1
    for lib, n in homes.items():
        if n > 1:
            problems["check1"].append(f"여러 곳에 나옴: {lib}")
    by_lib: dict[str, list] = {}
    for p in parts:
        by_lib.setdefault(p["library"], []).append(p)
    for lib in by_lib:
        if lib not in homes:
            problems["check1"].append(f"분류 체계에 없는 라이브러리: {lib}")
    for lib in homes:
        if lib not in by_lib:
            problems["check1"].append(f"카탈로그에 없는 라이브러리: {lib}")
    cov = Counter()
    for lib, ps in by_lib.items():
        if lib in libs:
            pr = libs[lib].get("part_rules") or {}
            for p in ps:     # 부분 이름 규칙이 걸리는 부품은 '이름 규칙', 나머지는 라이브러리 상태
                cov["rule" if pr and match_rule(pr, p["name"], "_-") else libs[lib]["status"]] += 1
        elif lib in generic:
            for p in ps:
                if match_rule(generic[lib], p["name"]) is None:
                    problems["check1"].append(f"이름 규칙에 안 걸림: {lib}:{p['name']}")
                    cov["unmapped"] += 1
                else:
                    cov["rule"] += 1
        elif lib in unmapped:
            cov["unmapped"] += len(ps)
    # --- 검사 2: 기능 하나, 상태, 확인자
    for lib, e in libs.items():
        if e["function"] not in funcs:
            problems["check2"].append(f"{lib}: 없는 기능 {e['function']}")
        if e["status"] not in STATUSES:
            problems["check2"].append(f"{lib}: 알 수 없는 상태 {e['status']}")
        if e["status"] == "confirmed" and not str(e.get("approver", "")).startswith(("delegated:", "human:")):
            problems["check2"].append(f"{lib}: 확정인데 확인자 표시가 없음")
        own = funcs.get(e["function"], {}).get("domain")
        for d in e.get("also_ok", []):
            if d not in domains or d == own:
                problems["check2"].append(f"{lib}: also_ok 가 잘못됨({d})")
        also = e.get("also_functions", [])
        for fid in also + [r["function"] for r in (e.get("part_rules") or {}).values()]:
            if fid not in funcs:
                problems["check2"].append(f"{lib}: 없는 기능 {fid} (also_functions·part_rules)")
        derived = {funcs[f]["domain"] for f in also if f in funcs} - {own}
        if set(e.get("also_ok", [])) != derived:
            problems["check2"].append(f"{lib}: also_ok 가 also_functions 의 도메인과 다름")
        if (also or e.get("part_rules")) and not e.get("mixed"):
            problems["check2"].append(f"{lib}: also_functions·part_rules 가 있는데 mixed 표시가 없음")
        if e.get("mixed") and not (also or e.get("part_rules")):
            problems["check2"].append(f"{lib}: mixed 인데 also_functions·part_rules 가 없음")
    for lib, rules in generic.items():
        for key, r in rules.items():
            if r["function"] not in funcs:
                problems["check2"].append(f"{lib}:{key}: 없는 기능 {r['function']}")
    # --- 검사 3: DigiKey 번호(참고 파일이 있을 때만)
    skipped3 = ref is None or digikey_ids is None
    if not skipped3:
        used = set(ref.get("libraries", {}).values()) | {i for v in ref.get("functions", {}).values() for i in v}
        for i in sorted(used - digikey_ids):
            problems["check3"].append(f"DigiKey 분류 원본에 없는 번호: {i}")
        for lib in ref.get("libraries", {}):
            if lib not in libs:
                problems["check3"].append(f"참고 파일의 라이브러리가 분류 체계에 없음: {lib}")
    total = sum(cov.values())
    return {"problems": problems, "check3_skipped": skipped3, "parts_total": total,
            "coverage": {k: (v, round(v / total * 100, 1) if total else 0.0) for k, v in sorted(cov.items())}}


def digikey_ids_from_raw(raw: dict) -> set:
    out = set()

    def walk(c):
        out.add(c.get("CategoryId"))
        for ch in c.get("Children") or []:
            walk(ch)
    for top in raw.get("Categories") or []:
        walk(top)
    return out


def main():
    sys.path.insert(0, str(ROOT))
    import kicad_parts as kp
    tax = json.loads(TAXONOMY.read_text(encoding="utf-8"))
    parts = [{"library": p["library"], "name": p["name"]} for p in kp.default_catalog()]
    ref = json.loads(REF.read_text(encoding="utf-8")) if REF.exists() else None
    ids = digikey_ids_from_raw(json.loads(RAW.read_text(encoding="utf-8"))) if RAW.exists() else None
    res = validate(tax, parts, ref, ids)
    if "--json" in sys.argv:
        print(json.dumps(res, ensure_ascii=False, indent=1))
    else:
        for k, msgs in res["problems"].items():
            print(f"{k}: {'통과' if not msgs else str(len(msgs)) + '건 실패'}" + (" (건너뜀: 참고 파일 없음)" if k == "check3" and res["check3_skipped"] else ""))
            for m in msgs[:10]:
                print("   -", m)
        print(f"check4 적용 범위(부품 {res['parts_total']:,}개):", {k: f"{v[0]:,} ({v[1]}%)" for k, v in res["coverage"].items()})
    return 1 if any(res["problems"].values()) else 0


if __name__ == "__main__":
    sys.exit(main())
