#!/usr/bin/env python3
"""명세 1 봉인 판정(읽기 전용): 98 라벨로 제외 규칙을 적용하고 꺼짐·켬 결과를 짝 비교해 사전 등록 기준 ①~④ 를 판정한다.

사용: .venv/bin/python scripts/compare-spec1.py --questions data/eval/spec1/questions-sealed.jsonl --labels data/eval/spec1-label/labels-98.jsonl \
        --key data/eval/spec1/label-key-sealed.json --off RESULT_OFF --on RESULT_ON --prac-off ... --prac-on ... --questions-prac ...
"""
from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from pathlib import Path

PARTS = {"part_search", "part_alternative", "part_mix"}


def load(p):
    return [json.loads(l) for l in Path(p).read_text(encoding="utf-8").splitlines() if l.strip()]


def sign_p(b: int, c: int) -> float:
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(0, k + 1)) / 2 ** n)


def excluded(q, lab, reasons):
    exp_parts = q["kind"] == "parts"
    if lab.get("unsure"):
        reasons["unsure"] += 1
        return True
    if (lab["intent"] in PARTS) != exp_parts:
        reasons["intent 불일치"] += 1
        return True
    if exp_parts and not (set(lab.get("libs") or []) & set(q["gold_libs"])):
        reasons["라이브러리 불일치"] += 1
        return True
    return False


def effect(qs, off, on):
    sel = [q for q in qs if q["kind"] == "parts" and not q.get("lib_leak")]
    b = sum(1 for q in sel if on[q["id"]]["hit"] and not off[q["id"]]["hit"])
    c = sum(1 for q in sel if off[q["id"]]["hit"] and not on[q["id"]]["hit"])
    return len(sel), b, c


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--questions", required=True); ap.add_argument("--labels", required=True); ap.add_argument("--key", required=True)
    ap.add_argument("--off", required=True); ap.add_argument("--on", required=True)
    ap.add_argument("--questions-prac", required=True); ap.add_argument("--prac-off", required=True); ap.add_argument("--prac-on", required=True)
    a = ap.parse_args()
    qs = load(a.questions); key = json.loads(Path(a.key).read_text(encoding="utf-8"))
    labs = {key[l["id"]]: l for l in load(a.labels)}
    off = {r["id"]: r for r in load(a.off)}; on = {r["id"]: r for r in load(a.on)}
    reasons = Counter(); keep = []
    lib_by_domain = Counter()
    for q in qs:
        if excluded(q, labs[q["id"]], reasons):
            if q["kind"] == "parts" and (labs[q["id"]]["intent"] in PARTS) and not labs[q["id"]].get("unsure"):
                lib_by_domain[q.get("domain", "?")] += 1
            continue
        keep.append(q)
    out = [f"봉인 질문 {len(qs)}개 · 제외 {len(qs) - len(keep)}개({len(qs) and (len(qs) - len(keep)) / len(qs):.1%}) 이유: {dict(reasons)} · 라이브러리 불일치의 영역별: {dict(lib_by_domain)}"]
    hold = (len(qs) - len(keep)) / len(qs) > 0.25
    out.append("판정 보류(제외 25% 초과)" if hold else "제외 25% 이하 — 판정 진행")
    n, b, c = effect(keep, off, on)
    n_all, b_all, c_all = effect(qs, off, on)
    notp = [q for q in keep if q["kind"] == "not_parts"]
    mis_off = sum(1 for q in notp if off[q["id"]]["answered"]); mis_on = sum(1 for q in notp if on[q["id"]]["answered"])
    pq = load(a.questions_prac); poff = {r["id"]: r for r in load(a.prac_off)}; pon = {r["id"]: r for r in load(a.prac_on)}
    pn, pb, pc = effect(pq, poff, pon)
    prac_eff = (pb - pc) / pn * 100; seal_eff = (b - c) / n * 100 if n else 0
    out += [f"[제외 후] 부품 질문(순환 제외) {n}: 켬만 맞음 b={b} · 끔만 맞음 c={c} · 양측 정확 p={sign_p(b, c):.3f} · 효과 {seal_eff:+.1f}/100",
            f"[민감도: 제외 전 207 전체] 부품 {n_all}: b={b_all} c={c_all} p={sign_p(b_all, c_all):.3f}",
            f"[비부품 {len(notp)}] 오처리 꺼짐 {mis_off} · 켬 {mis_on} · 5% 상한(내림) {math.floor(len(notp) * 0.05)}",
            f"[연습] 부품 {pn}: b={pb} c={pc} 효과 {prac_eff:+.1f}/100"]
    ok1 = (b - c) >= 5 and b >= 2 * c
    ok2 = c <= 3
    ok3 = mis_on <= mis_off + 1 and mis_on <= math.floor(len(notp) * 0.05)
    ok4 = (prac_eff - seal_eff) <= 8 and seal_eff >= prac_eff / 2
    out += [f"기준 ① 개선(b−c≥5, b≥2c): {'충족' if ok1 else '미충족'}", f"기준 ② 후퇴 없음(c≤3): {'충족' if ok2 else '미충족'}",
            f"기준 ③ 오처리: {'충족' if ok3 else '미충족'}", f"기준 ④ 과적합(연습−봉인≤8, 봉인≥연습/2): {'충족' if ok4 else '미충족'}"]
    out.append("종합: " + ("보류(라벨 제외 초과)" if hold else ("모두 충족" if ok1 and ok2 and ok3 and ok4 else "미충족 — 켜지 않음")))
    # 칸별 보고
    def cell(name, f):
        sel = [q for q in keep if q["kind"] == "parts" and not q.get("lib_leak") and f(q)]
        if sel:
            bb = sum(1 for q in sel if on[q["id"]]["hit"] and not off[q["id"]]["hit"]); cc = sum(1 for q in sel if off[q["id"]]["hit"] and not on[q["id"]]["hit"])
            h0 = sum(off[q["id"]]["hit"] for q in sel); h1 = sum(on[q["id"]]["hit"] for q in sel)
            out.append(f"  {name}: {len(sel)} 끔 적중 {h0} 켬 적중 {h1} (b={bb}, c={cc})")
    for it in ("A1", "A2", "A3"):
        cell(f"의도 {it}", lambda q, it=it: q["intent"] == it)
    for fr in ("B1", "B2", "B3", "B4", "B5"):
        cell(f"틀 {fr}", lambda q, fr=fr: q["frame"] == fr)
    cell("C2·C3", lambda q: q.get("cond", 0) >= 2)
    cell("A2 카탈로그에 있는 이름", lambda q: q["intent"] == "A2" and q.get("pn_in_catalog") is True)
    cell("A2 카탈로그에 없는 이름", lambda q: q["intent"] == "A2" and q.get("pn_in_catalog") is False)
    e4 = [q for q in notp if q.get("E") == "E4"]
    out.append(f"  A6×E4 비부품 {len(e4)}: 오처리 꺼짐 {sum(off[q['id']]['answered'] for q in e4)} 켬 {sum(on[q['id']]['answered'] for q in e4)}")
    print("\n".join(out))


if __name__ == "__main__":
    main()
