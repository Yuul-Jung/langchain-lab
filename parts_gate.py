"""부품 질문 관문의 보조 거부(학습 모델).

규칙 관문이 "부품 질문"이라고 판단한 뒤에만 쓴다. 질문 임베딩으로 학습한 로지스틱 회귀가
부품 질문일 확률을 아주 낮게(< 문턱) 볼 때만 "부품 질문 아님"으로 되돌린다. 규칙이 먼저이고,
이 모델은 부품 질문을 새로 받아들이지 않는다.

- 모델: data/parts_gate/model.npz (w, b, tau) — scripts/train-parts-gate.py 로 만든다(이 PC 전용, git 밖).
- 문턱(tau): 학습 자료 5겹 교차검증에서 부품 질문의 가장 낮은 확률 − 0.02 (부품 질문을 하나도 거부하지 않는 값).
- 설정 PARTS_GATE_ML (기본 켜짐). 모델 파일·임베딩이 없거나 실패하면 조용히 거부하지 않는다(원래 동작).
"""
from __future__ import annotations

import math
from pathlib import Path

import settings

ROOT = Path(__file__).resolve().parent
MODEL = ROOT / "data" / "parts_gate" / "model.npz"
_cache: dict = {}


def _load(path: Path):
    key = str(path)
    if key not in _cache:
        try:
            import numpy as np
            m = np.load(path)
            _cache[key] = (np.asarray(m["w"], dtype=float), float(m["b"]), float(m["tau"]))
        except Exception:
            _cache[key] = None          # 한 번 실패하면 다시 읽지 않는다
    return _cache[key]


def probability(question: str, embed, model) -> float:
    import numpy as np
    w, b, _ = model
    v = np.asarray(embed(question), dtype=float)
    n = float(np.linalg.norm(v))
    if v.shape != w.shape or n == 0.0:
        raise ValueError("임베딩 차원이 모델과 다릅니다.")
    return 1.0 / (1.0 + math.exp(-(float(v @ w) / n + b)))


def veto(question: str, embed=None, path: Path | None = None) -> bool:
    """True 이면 '부품 질문 아님'으로 되돌린다. 확실하지 않거나 실패하면 False."""
    if not getattr(settings, "PARTS_GATE_ML", True):
        return False
    model = _load(path or MODEL)
    if model is None:
        return False
    try:
        if embed is None:
            import rag_search
            embed = rag_search.embed_query
        return probability(question, embed, model) < model[2]
    except Exception:
        return False
