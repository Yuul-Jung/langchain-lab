#!/usr/bin/env python3
"""'대체품 추천 요청인가'를 가리는 학습 관문을 만든다 (substitute_gate.py 가 읽는 data/substitute_gate/model.npz).

기준 부품 고정(PARTS_ANCHOR_LOCK)이 켜졌을 때, 질문에 부품 번호와 대체·교체·호환 같은 말이 함께 있어도 그것이 '대체품을 추천해 달라'는
요청인지(1) 수리·사양·설명·구매 같은 다른 질문인지(0)를 질문 임베딩으로 가린다. 낱말 규칙을 덧붙이는 방식이 새 대조 문장에서 계속 깨졌기 때문이다
(2차 판정 기준 2 미충족, 동료 검토의 대조 탐침 32개 중 25개 오처리).

학습 자료(모두 이미 공개·은퇴한 것만 쓴다. 판정에 쓸 봉인 낱말 목록은 쓰지 않는다): 1차·2차·3차 질문 세트, 동료 검토의 탐침. 이 PC 전용(data/ 는 git 밖).
부품 번호는 자리표시로 가린 뒤 임베딩한다(번호가 아니라 말투를 배우게). 평가는 표현 틀 단위로 묶어 나눈 교차검증(같은 틀이 학습과 평가에 함께 들어가지 않게).
문턱: 틀 단위 교차검증에서 '어려운 0'(부품 번호나 대체류 낱말이 든 대조 문장)이 통과하는 비율이 --far 이하가 되는 가장 낮은 값.

  .venv/bin/python scripts/train-substitute-gate.py [--far 0.02]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
OUT = ROOT / "data" / "substitute_gate"
EV = ROOT / "data" / "eval"


def jl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def examples() -> list[dict]:
    rows = []
    for name in ("practice", "sealed"):                                   # 2차: 대체 질문 1, 대조 0
        for q in jl(EV / "spec1-r2" / f"questions-{name}.jsonl"):
            if q["kind"] in ("substitute", "control"):
                rows.append({"q": q["question"], "y": int(q["kind"] == "substitute"), "group": "r2:" + q["template"], "hard": q["kind"] == "control"})
    for q in jl(EV / "spec1-r2" / "questions-extra.jsonl"):               # 2차: 두 부품 질문(호환 여부·차이) 0
        if q["kind"] == "borderline":
            rows.append({"q": q["question"], "y": 0, "group": "r2:" + q["template"], "hard": True})
    r3 = EV / "spec1-r3"                                                  # 3차(은퇴한 봉인): 대체 질문 1, 대조·두 부품 질문 0
    if (r3 / "questions-sealed.jsonl").exists():
        for q in jl(r3 / "questions-sealed.jsonl") + jl(r3 / "questions-extra.jsonl"):
            if q["kind"] in ("substitute", "control", "two_part"):
                rows.append({"q": q["question"], "y": int(q["kind"] == "substitute"), "group": "r3:" + q["template"], "hard": q["kind"] != "substitute"})
    for name in ("practice", "sealed"):                                   # 1차: 영문 부품 대체 질문 1, 부품 아닌 질문 0
        for q in jl(EV / "spec1" / f"questions-{name}.jsonl"):
            if q["kind"] == "parts" and q["intent"] == "A2":
                rows.append({"q": q["question"], "y": 1, "group": f"r1:A2:{q['frame']}:{q.get('cond', 0)}", "hard": False})
            elif q["kind"] == "not_parts":
                rows.append({"q": q["question"], "y": 0, "group": f"r1:{q['intent']}:{q['frame']}", "hard": q["intent"] == "A4"})
    probes = EV / "spec1-r2" / "labeler-work" / "review3" / "probes.txt"  # 동료 검토의 탐침: A 대체 요청 아님 0, B 진짜 대체 요청 1
    if probes.exists():
        section = ""
        for line in probes.read_text(encoding="utf-8").splitlines():
            if line.startswith("# ---"):
                section = line.split("---")[1].strip()[:1]
            elif "|" in line and not line.startswith("#") and section in ("A", "B"):
                tag, q = line.split("|", 1)
                rows.append({"q": q.strip(), "y": int(section == "B"), "group": "probe:" + tag.strip(), "hard": section == "A"})
    seen, out = set(), []
    for r in rows:
        if r["q"] not in seen:
            seen.add(r["q"])
            out.append(r)
    return out


def mask(question: str, catalog) -> str:
    """부품 번호 낱말을 자리표시로 바꾼다(서비스가 관문에 넣는 글과 같은 함수)."""
    import parts_graph as pg
    return pg.mask_numbers(question, pg.part_tokens_in(question, catalog))


def embed_all(texts: list[str]) -> np.ndarray:
    import rag_search
    OUT.mkdir(parents=True, exist_ok=True)
    cache_path = OUT / "emb_cache.json"
    cache = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}
    for i, t in enumerate(texts):
        k = hashlib.sha256(t.encode("utf-8")).hexdigest()
        if k not in cache:
            cache[k] = [round(float(x), 6) for x in rag_search.embed_query(t)]
            if i % 100 == 0:
                cache_path.write_text(json.dumps(cache), encoding="utf-8")
    cache_path.write_text(json.dumps(cache), encoding="utf-8")
    X = np.array([cache[hashlib.sha256(t.encode("utf-8")).hexdigest()] for t in texts], dtype=float)
    return X / np.linalg.norm(X, axis=1, keepdims=True)


def fit(X, y, l2=1e-3, steps=1500, lr=4.0):
    w, b = np.zeros(X.shape[1]), 0.0
    wt = np.where(y == 1, 0.5 / max(y.sum(), 1), 0.5 / max((1 - y).sum(), 1)) * len(y)     # 두 쪽을 같은 무게로
    for _ in range(steps):
        g = (1 / (1 + np.exp(-(X @ w + b))) - y) * wt
        w -= lr * (X.T @ g / len(y) + l2 * w)
        b -= lr * g.mean()
    return w, b


def group_cv(X, y, groups, folds=8, seed=0):
    """표현 틀(group) 단위로 나눈 교차검증의 평가 쪽 확률."""
    names = sorted(set(groups))
    order = np.random.default_rng(seed).permutation(len(names))
    fold_of = {names[j]: i % folds for i, j in enumerate(order)}
    f = np.array([fold_of[g] for g in groups])
    out = np.zeros(len(y))
    for k in range(folds):
        w, b = fit(X[f != k], y[f != k])
        out[f == k] = 1 / (1 + np.exp(-(X[f == k] @ w + b)))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--far", type=float, default=0.02, help="교차검증에서 어려운 대조 문장이 통과해도 되는 비율(--tau 를 주지 않을 때)")
    ap.add_argument("--tau", type=float, default=None, help="문턱을 직접 정한다(교차검증 표를 보고 정한 값)")
    a = ap.parse_args()
    import kicad_parts as kp
    cat = kp.default_catalog()
    rows = examples()
    for r in rows:
        r["masked"] = mask(r["q"], cat)
    X = embed_all([r["masked"] for r in rows])
    y = np.array([r["y"] for r in rows], dtype=float)
    groups = [r["group"] for r in rows]
    hard = np.array([r["hard"] for r in rows])
    print(f"자료 {len(rows)}개: 대체 요청 {int(y.sum())}(틀 {len({g for g, r in zip(groups, rows) if r['y']})}가지) · 아닌 것 {int((1 - y).sum())}"
          f"(그중 어려운 것 {int(hard.sum())}, 틀 {len({g for g, r in zip(groups, rows) if not r['y']})}가지)")
    p = np.mean([group_cv(X, y, groups, seed=s) for s in range(3)], axis=0)
    hard_p = np.sort(p[hard])[::-1]
    allow = int(a.far * len(hard_p))
    tau = float(hard_p[allow] + 1e-6) if allow < len(hard_p) else 0.5
    tau = max(tau, 0.5) if a.tau is None else a.tau
    for t in sorted({0.5, 0.7, 0.9, round(tau, 4)}):
        print(f"문턱 {t:.3f}: 대체 요청 통과 {int((p[y == 1] >= t).sum())}/{int(y.sum())} = {(p[y == 1] >= t).mean():.1%} | "
              f"어려운 대조 통과 {int((p[hard] >= t).sum())}/{int(hard.sum())} = {(p[hard] >= t).mean():.1%} | "
              f"쉬운 대조 통과 {int((p[(y == 0) & ~hard] >= t).sum())}/{int(((y == 0) & ~hard).sum())}")
    by = defaultdict(list)
    for r, pi in zip(rows, p):
        by[r["group"]].append((pi, r))
    miss = sorted(((np.mean([x for x, _ in v]), g, v[0][1]["q"]) for g, v in by.items() if v[0][1]["y"] == 1 and np.mean([x for x, _ in v]) < tau))
    leak = sorted(((np.mean([x for x, _ in v]), g, v[0][1]["q"]) for g, v in by.items() if v[0][1]["y"] == 0 and np.mean([x for x, _ in v]) >= tau), reverse=True)
    print(f"채택 문턱 {tau:.3f} — 놓치는 대체 틀 {len(miss)}가지:")
    for m in miss[:15]:
        print(f"   {m[0]:.2f} {m[1]} | {m[2][:60]}")
    print(f"통과하는 대조 틀 {len(leak)}가지:")
    for m in leak[:15]:
        print(f"   {m[0]:.2f} {m[1]} | {m[2][:60]}")
    w, b = fit(X, y)
    np.savez(OUT / "model.npz", w=w, b=b, tau=tau)
    print(f"저장: {OUT / 'model.npz'} (문턱 {tau:.3f}, 학습 자료 {len(rows)}개, 틀 {len(set(groups))}가지)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
