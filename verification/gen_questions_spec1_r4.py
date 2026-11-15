#!/usr/bin/env python3
"""명세 1 4차 판정 질문 생성기(결정적). 규칙은 static_data/verification/spec1_round4_preregistration.md 3절.

입력: verification/spec1_lexicon_r4.json (저장소를 읽지 않은 새 하위 에이전트가 쓴 낱말 목록), 카탈로그(번호가 찾아지는지 기계적으로 분류),
      1차·2차·3차 낱말 목록(이미 본 번호를 봉인에서 빼는 데만 씀).
출력: data/eval/spec1-r4/questions-{sealed,extra}.jsonl (data/ 는 git 에 올리지 않는다).
사용: .venv/bin/python verification/gen_questions_spec1_r4.py [--lexicon 파일] [--out 폴더]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))
import kicad_parts as kp  # noqa: E402
import spec1_lexicon as lex1  # noqa: E402

PHRASE = "spec1-bundle-split-v4"
SEAL_FOUND, SEAL_MISSING, PAIRS_PER_TEMPLATE = 40, 20, 4
SLOT = {"V": "v", "PKG": "pkg", "IF": "if"}
AREAS = {"전원", "아날로그", "논리", "MCU", "메모리", "통신", "센서", "구동", "개별 반도체", "수동", "커넥터"}


def h(*parts: str) -> str:
    return hashlib.sha256("|".join((PHRASE,) + parts).encode("utf-8")).hexdigest()


def fill(text: str, part: dict, pn2: str = "") -> str:
    return (text.replace("{PN2}", pn2).replace("{PN}", part["pn"]).replace("{V}", part.get("v", ""))
            .replace("{PKG}", part.get("pkg", "")).replace("{IF}", part.get("if", "")))


def eligible(t: dict, part: dict) -> bool:
    return all(part.get(SLOT[n]) for n in t.get("needs", [])) and (not t.get("areas") or part["area"] in t["areas"])


def cond_text(t: dict, part: dict) -> str:
    """질문이 단 조건(라벨 행을 묶는 열쇠). 조건 없는 틀은 빈 글."""
    if not t.get("has_condition"):
        return ""
    return ";".join([f"틀 {t['id']}"] + [f"{n}={part[SLOT[n]]}" for n in t.get("needs", [])])


def check(d: dict) -> list[str]:
    """낱말 목록의 형식 점검(내용은 고치지 않는다). 문제를 글로 돌려준다."""
    bad = []
    for key in ("parts", "substitute_templates", "control_templates", "no_anchor_templates", "two_part_templates"):
        if not isinstance(d.get(key), list) or not d[key]:
            bad.append(f"{key} 없음")
    for p in d.get("parts", []):
        if not p.get("pn") or p.get("area") not in AREAS:
            bad.append(f"부품 형식: {p.get('pn')!r} {p.get('area')!r}")
    for key in ("substitute_templates", "control_templates", "no_anchor_templates", "two_part_templates"):
        ids = [t.get("id") for t in d.get(key, [])]
        if len(ids) != len(set(ids)):
            bad.append(f"{key} id 중복")
    for t in d.get("substitute_templates", []):
        if "{PN}" not in t.get("text", ""):
            bad.append(f"{t.get('id')}: {{PN}} 없음")
        for n in t.get("needs", []):
            if n not in SLOT or "{" + n + "}" not in t["text"]:
                bad.append(f"{t.get('id')}: 슬롯 {n} 불일치")
    for t in d.get("control_templates", []):
        if bool(t.get("needs_pn")) != ("{PN}" in t.get("text", "")):
            bad.append(f"{t.get('id')}: needs_pn 불일치")
    for t in d.get("two_part_templates", []):
        if "{PN}" not in t.get("text", "") or "{PN2}" not in t.get("text", ""):
            bad.append(f"{t.get('id')}: 번호 자리 둘이 아님")
    return bad


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lexicon", type=Path, default=HERE / "spec1_lexicon_r4.json")
    ap.add_argument("--out", type=Path, default=ROOT / "data" / "eval" / "spec1-r4")
    a = ap.parse_args()
    d = json.loads(a.lexicon.read_text(encoding="utf-8"))
    bad = check(d)
    if bad:
        print("낱말 목록 형식 문제(해당 항목은 빼고 진행):", *bad[:20], sep="\n  ")
    catalog = kp.default_catalog()
    seen = {pn.lower() for items in lex1.D_ITEMS.values() for it in items for pn in it["pn"]}
    seen |= {p["pn"].lower() for p in json.loads((HERE / "spec1_lexicon_r2.json").read_text(encoding="utf-8"))["parts"]}
    seen |= {p["pn"].lower() for p in json.loads((HERE / "spec1_lexicon_r3.json").read_text(encoding="utf-8"))["parts"]}
    parts, dup = [], set()
    for p in d["parts"]:
        if not p.get("pn") or p.get("area") not in AREAS or p["pn"].lower() in dup:
            continue
        dup.add(p["pn"].lower())
        found = bool(list(kp._candidate_groups(f"{p['pn']} 대체품", catalog)))
        parts.append({**p, "found": found, "seen": p["pn"].lower() in seen, "order": h("pn", p["pn"])})
    parts.sort(key=lambda p: p["order"])
    new_found = [p for p in parts if p["found"] and not p["seen"]][:SEAL_FOUND]
    new_missing = [p for p in parts if not p["found"] and not p["seen"]][:SEAL_MISSING]
    subs = [t for t in d["substitute_templates"] if "{PN}" in t.get("text", "")]
    plain = [t for t in subs if not t.get("has_condition")]
    conds = [t for t in subs if t.get("has_condition")]

    questions = []
    for found, group in ((True, new_found), (False, new_missing)):
        used = Counter()
        for i, p in enumerate(group):
            offset = 0 if found else len(plain) // 2
            picks = [plain[(i + offset) % len(plain)]]
            ok = sorted((t for t in conds if eligible(t, p)), key=lambda t: (used[t["id"]], h("cond", p["pn"], t["id"])))
            if ok:
                picks.append(ok[0])
                used[ok[0]["id"]] += 1
            else:
                picks.append(plain[(i + offset + len(plain) // 3 + 1) % len(plain)])
            for t in picks:
                questions.append({"id": f"r4-{t['id']}-{p['pn']}", "kind": "substitute", "split": "sealed", "pn": p["pn"], "pn_found": found,
                                  "template": t["id"], "cond": cond_text(t, p), "area": p["area"], "fn": p.get("fn", ""), "label": True,
                                  "question": fill(t["text"], p)})
    for t in d["control_templates"]:
        if not t.get("needs_pn"):
            questions.append({"id": f"r4-{t['id']}", "kind": "control", "split": "sealed", "template": t["id"], "category": t.get("category", ""),
                              "question": t["text"]})
            continue
        pool = sorted((p for p in parts if not t.get("areas") or p["area"] in t["areas"]), key=lambda p: h("control", t["id"], p["pn"]))
        for p in [x for x in pool if x["found"]][:1] + [x for x in pool if not x["found"]][:1]:
            questions.append({"id": f"r4-{t['id']}-{p['pn']}", "kind": "control", "split": "sealed", "template": t["id"],
                              "category": t.get("category", ""), "pn": p["pn"], "pn_found": p["found"], "question": fill(t["text"], p)})
    for t in d["no_anchor_templates"]:
        questions.append({"id": f"r4-{t['id']}", "kind": "no_anchor", "split": "sealed", "template": t["id"], "question": t["text"]})
    extra = []
    for t in d["two_part_templates"]:
        for p in sorted((p for p in parts if p["found"]), key=lambda p: h("pair", t["id"], p["pn"]))[:PAIRS_PER_TEMPLATE]:
            mates = sorted((x for x in parts if x["area"] == p["area"] and x["pn"] != p["pn"]), key=lambda x: h("mate", t["id"], p["pn"], x["pn"]))
            if mates:
                extra.append({"id": f"r4-{t['id']}-{p['pn']}", "kind": "two_part", "split": "extra", "template": t["id"],
                              "category": t.get("category", ""), "pn": p["pn"], "pn2": mates[0]["pn"], "question": fill(t["text"], p, mates[0]["pn"])})

    a.out.mkdir(parents=True, exist_ok=True)
    ids = [q["id"] for q in questions + extra]
    assert len(ids) == len(set(ids)), "질문 id 중복"
    print(f"부품 번호 {len(parts)}개: 찾아짐 {sum(p['found'] for p in parts)} · 이미 본 번호 {sum(p['seen'] for p in parts)} · "
          f"새 번호 찾아짐 {sum(p['found'] and not p['seen'] for p in parts)} · 새 번호 안 찾아짐 {sum(not p['found'] and not p['seen'] for p in parts)}")
    for name, rows in (("sealed", questions), ("extra", extra)):
        path = a.out / f"questions-{name}.jsonl"
        path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
        sub = [r for r in rows if r["kind"] == "substitute"]
        print(f"{name}: 질문 {len(rows)} | 대체 질문 {len(sub)} (찾아짐 {sum(r['pn_found'] for r in sub)} · 안 찾아짐 {sum(not r['pn_found'] for r in sub)}, "
              f"조건 있는 질문 {sum(bool(r['cond']) for r in sub)}, 틀 {len({r['template'] for r in sub})}가지) | 대조 {sum(r['kind'] == 'control' for r in rows)}"
              f" | 번호 없는 부품 질문 {sum(r['kind'] == 'no_anchor' for r in rows)} | 두 부품 {sum(r['kind'] == 'two_part' for r in rows)}"
              f" | sha256 {hashlib.sha256(path.read_bytes()).hexdigest()[:16]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
