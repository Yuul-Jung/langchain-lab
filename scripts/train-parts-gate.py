#!/usr/bin/env python3
"""부품 질문 관문의 보조 거부 모델을 학습한다 (parts_gate.py 가 읽는 data/parts_gate/model.npz).

학습 자료: data/eval 의 은퇴한(이미 판정에 다 쓴) 부품 질문 세트. 봉인 중인 세트는 넣지 않는다.
  --train 으로 파일을 지정한다. 질문의 kind(parts / not_parts)가 정답이다.
문턱: 5겹 교차검증에서 부품 질문의 가장 낮은 확률 − 0.02 (교차검증에서 부품 질문을 하나도 거부하지 않는 값).
임베딩은 LM Studio(rag_search.embed_query)로 얻고 data/parts_gate/emb_cache.json 에 저장한다.

  .venv/bin/python scripts/train-parts-gate.py --train data/eval/parts-ko-questions.jsonl data/eval/parts-ko-questions-71.jsonl ...
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
OUT = ROOT / "data" / "parts_gate"
MARGIN = 0.02


def load(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            d = json.loads(line)
            if d.get("kind") in ("parts", "not_parts"):
                rows.append(d)
    return rows


def fit(X, y, l2=1e-4, steps=4000, lr=2.0):
    w, b = np.zeros(X.shape[1]), 0.0
    for _ in range(steps):
        g = 1 / (1 + np.exp(-(X @ w + b))) - y
        w -= lr * (X.T @ g / len(y) + l2 * w)
        b -= lr * g.mean()
    return w, b


def cv_probabilities(X, y, folds=5, seed=0):
    idx = np.random.default_rng(seed).permutation(len(y))
    parts, out = np.array_split(idx, folds), np.zeros(len(y))
    for k in range(folds):
        test = parts[k]
        train = np.concatenate([parts[j] for j in range(folds) if j != k])
        w, b = fit(X[train], y[train])
        out[test] = 1 / (1 + np.exp(-(X[test] @ w + b)))
    return out


def threshold(cv_p, y) -> float:
    return float(cv_p[y == 1].min() - MARGIN)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--train", nargs="+", type=Path, required=True)
    args = ap.parse_args()
    import rag_search
    OUT.mkdir(parents=True, exist_ok=True)
    cache_path = OUT / "emb_cache.json"
    cache = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}
    rows = [r for f in args.train for r in load(f)]
    for r in rows:
        if r["question"] not in cache:
            cache[r["question"]] = rag_search.embed_query(r["question"])
    cache_path.write_text(json.dumps(cache), encoding="utf-8")
    X = np.array([cache[r["question"]] for r in rows], dtype=float)
    X /= np.linalg.norm(X, axis=1, keepdims=True)
    y = np.array([1 if r["kind"] == "parts" else 0 for r in rows])
    cv_p = cv_probabilities(X, y)
    tau = threshold(cv_p, y)
    w, b = fit(X, y)
    np.savez(OUT / "model.npz", w=w, b=b, tau=tau)
    neg = cv_p[y == 0]
    print(f"학습 {len(y)}개(부품 {int(y.sum())}) · 교차검증 정확도 {((cv_p >= 0.5) == (y == 1)).mean():.3f} · "
          f"문턱 {tau:.3f} → 교차검증에서 거부: 부품 0 · 부품 아님 {int((neg < tau).sum())}/{len(neg)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
