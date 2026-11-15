#!/usr/bin/env python3
"""명세 1 2차 판정 질문 생성기(결정적). 규칙은 static_data/verification/spec1_round2_preregistration.md 8절.

입력: verification/spec1_lexicon_r2.json (동료 세션이 코드를 보기 전에 쓴 낱말 목록), 카탈로그(번호가 찾아지는지 기계적으로 분류),
      verification/spec1_lexicon.py (1차 낱말 목록 — 겹치는 번호를 연습으로 돌리는 데만 씀).
출력: data/eval/spec1-r2/questions-{practice,sealed,extra}.jsonl (data/ 는 git 에 올리지 않는다).
사용: .venv/bin/python verification/gen_questions_spec1_r2.py
"""
from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import kicad_parts as kp  # noqa: E402
import spec1_lexicon as lex1  # noqa: E402

PHRASE = "spec1-bundle-split-v2-emb"
SEAL_FOUND, SEAL_MISSING, SEAL_CONTROL_TEMPLATES = 36, 18, 21
PRACTICE_LABELED = 18          # 연습의 찾아짐 번호 중 라벨을 달 개수(과적합 점검용)
OUT = ROOT / "data" / "eval" / "spec1-r2"


def h(*parts: str) -> str:
    return hashlib.sha256("|".join((PHRASE,) + parts).encode("utf-8")).hexdigest()


def fill(text: str, part: dict, pn2: str = "") -> str:
    return (text.replace("{PN2}", pn2).replace("{PN}", part["pn"]).replace("{V}", part.get("v", ""))
            .replace("{PKG}", part.get("pkg", "")).replace("{IF}", part.get("if", "")))


def eligible(t: dict, part: dict) -> bool:
    slot = {"V": "v", "PKG": "pkg", "IF": "if"}
    return all(part.get(slot[n]) for n in t.get("needs", [])) and (not t.get("areas") or part["area"] in t["areas"])


def cond_text(t: dict, part: dict) -> str:
    """질문이 단 조건(라벨 행을 묶는 열쇠). 조건 없는 틀은 빈 글."""
    if t["id"] <= "S28":
        return ""
    slot = {"V": "v", "PKG": "pkg", "IF": "if"}
    filled = [f"{n}={part[slot[n]]}" for n in t.get("needs", [])]
    return ";".join(filled) if filled else f"틀 {t['id']}"      # 고정 조건 틀(SMD·DIP·3.3V 동작·5V 전원·핀 호환)은 틀 번호로 구분


def main() -> int:
    d = json.loads((Path(__file__).resolve().parent / "spec1_lexicon_r2.json").read_text(encoding="utf-8"))
    catalog = kp.default_catalog()
    old = {pn.lower() for items in lex1.D_ITEMS.values() for it in items for pn in it["pn"]}
    parts = []
    for p in d["parts"]:
        found = bool(list(kp._candidate_groups(f"{p['pn']} 대체품", catalog)))
        parts.append({**p, "found": found, "overlap_r1": p["pn"].lower() in old, "order": h("pn", p["pn"])})
    parts.sort(key=lambda p: p["order"])
    new_found = [p for p in parts if p["found"] and not p["overlap_r1"]]
    new_missing = [p for p in parts if not p["found"] and not p["overlap_r1"]]
    sealed_pn = {p["pn"] for p in new_found[:SEAL_FOUND]} | {p["pn"] for p in new_missing[:SEAL_MISSING]}
    plain = [t for t in d["substitute_templates"] if t["id"] <= "S28"]
    conds = [t for t in d["substitute_templates"] if t["id"] > "S28"]

    questions = []
    for split in ("sealed", "practice"):
        for found in (True, False):
            group = [p for p in parts if (p["pn"] in sealed_pn) == (split == "sealed") and p["found"] == found]
            used = Counter()
            for i, p in enumerate(group):
                offset = 0 if found else 14
                picks = [plain[(i + offset) % len(plain)]]
                ok = sorted((t for t in conds if eligible(t, p)), key=lambda t: (used[t["id"]], h("cond", p["pn"], t["id"])))
                if ok:
                    picks.append(ok[0])
                    used[ok[0]["id"]] += 1
                else:
                    picks.append(plain[(i + offset + len(plain) // 2) % len(plain)])
                for t in picks:
                    questions.append({"id": f"r2-{t['id']}-{p['pn']}", "kind": "substitute", "split": split, "pn": p["pn"], "pn_found": found,
                                      "overlap_r1": p["overlap_r1"], "template": t["id"], "cond": cond_text(t, p), "area": p["area"],
                                      "fn": p["fn"], "question": fill(t["text"], p)})
    labeled = [p["pn"] for p in parts if p["pn"] not in sealed_pn and p["found"]][:PRACTICE_LABELED]
    for q in questions:
        q["label"] = q["split"] == "sealed" or q["pn"] in labeled

    # 대조 질문: 틀 단위로 나눈다
    ct = sorted(d["control_templates"], key=lambda t: h("control", t["id"]))
    start = 0
    while True:
        sealed_t = {t["id"] for t in ct[start:start + SEAL_CONTROL_TEMPLATES]}
        n = sum(3 if t.get("needs_pn") else 1 for t in ct if t["id"] in sealed_t)
        if n >= 34 or start + SEAL_CONTROL_TEMPLATES >= len(ct):
            break
        start += 1
    for t in d["control_templates"]:
        split = "sealed" if t["id"] in sealed_t else "practice"
        if not t.get("needs_pn"):
            questions.append({"id": f"r2-{t['id']}", "kind": "control", "split": split, "template": t["id"], "category": t["category"],
                              "question": t["text"]})
            continue
        pool = sorted((p for p in parts if not t.get("areas") or p["area"] in t["areas"]), key=lambda p: h("control", t["id"], p["pn"]))
        chosen = [p for p in pool if p["found"]][:2] + [p for p in pool if not p["found"]][:1]
        for p in chosen:
            questions.append({"id": f"r2-{t['id']}-{p['pn']}", "kind": "control", "split": split, "template": t["id"], "category": t["category"],
                              "pn": p["pn"], "pn_found": p["found"], "question": fill(t["text"], p)})

    # 설명용(판정 밖): 부품 번호 없는 부품 질문, 두 부품 질문
    extra = [{"id": f"r2-{t['id']}", "kind": "no_anchor", "split": "extra", "template": t["id"], "question": t["text"]}
             for t in d["no_anchor_templates"]]
    for t in d["borderline_templates"]:
        pool = sorted((p for p in parts if p["found"]), key=lambda p: h("border", t["id"], p["pn"]))[:6]
        for p in pool:
            mate = sorted((x for x in parts if x["area"] == p["area"] and x["pn"] != p["pn"]), key=lambda x: h("mate", t["id"], p["pn"], x["pn"]))[0]
            extra.append({"id": f"r2-{t['id']}-{p['pn']}", "kind": "borderline", "split": "extra", "template": t["id"], "pn": p["pn"],
                          "pn2": mate["pn"], "question": fill(t["text"], p, mate["pn"])})

    OUT.mkdir(parents=True, exist_ok=True)
    for name, rows in (("practice", [q for q in questions if q["split"] == "practice"]),
                       ("sealed", [q for q in questions if q["split"] == "sealed"]), ("extra", extra)):
        path = OUT / f"questions-{name}.jsonl"
        path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
        sub = [r for r in rows if r["kind"] == "substitute"]
        print(f"{name}: 질문 {len(rows)} | 대체 질문 {len(sub)} (찾아짐 {sum(r['pn_found'] for r in sub)} · 안 찾아짐 {sum(not r['pn_found'] for r in sub)}"
              f" · 라벨 대상 {sum(bool(r.get('label')) for r in sub)}) | 대조 {sum(r['kind'] == 'control' for r in rows)}"
              f" | 틀 {len({r['template'] for r in sub})}가지 | sha256 {hashlib.sha256(path.read_bytes()).hexdigest()[:16]}")
    print("봉인 대조 틀:", sorted(sealed_t), "창 시작", start)
    ids = [q["id"] for q in questions + extra]
    assert len(ids) == len(set(ids)), "질문 id 중복"
    return 0


if __name__ == "__main__":
    sys.exit(main())
