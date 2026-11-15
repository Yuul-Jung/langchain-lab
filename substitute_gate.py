"""'대체품 추천 요청인가'를 가리는 학습 관문 (기준 부품 고정·'카탈로그에 없음' 안내에서 쓴다).

질문에 부품 번호와 대체·교체·호환 같은 말이 함께 있어도, 그것이 대체품을 추천해 달라는 요청인지 수리·사양·설명·구매 같은 다른 질문인지는
낱말 규칙으로 가르기 어렵다(2차 판정에서 낱말 규칙이 대조 문장을 잡았고, 규칙을 덧붙여도 새 대조 문장에서 다시 깨졌다).
부품 번호를 자리표시로 가린 질문의 임베딩으로 학습한 로지스틱 회귀가 확률을 내고, 문턱 이상일 때만 요청으로 본다.

- 모델: data/substitute_gate/model.npz (w, b, tau) — scripts/train-substitute-gate.py 로 만든다(이 PC 전용, git 밖).
- 모델 파일·임베딩이 없거나 실패하면 None 을 돌려준다(부르는 쪽이 원래의 좁은 규칙으로 돌아간다).
"""
from __future__ import annotations

import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MODEL = ROOT / "data" / "substitute_gate" / "model.npz"
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


def probability(masked_question: str, embed, model) -> float:
    import numpy as np
    w, b, _ = model
    v = np.asarray(embed(masked_question), dtype=float)
    n = float(np.linalg.norm(v))
    if v.shape != w.shape or n == 0.0:
        raise ValueError("임베딩 차원이 모델과 다릅니다.")
    return 1.0 / (1.0 + math.exp(-(float(v @ w) / n + b)))


def decide(masked_question: str, embed=None, path: Path | None = None) -> bool | None:
    """True 대체품 추천 요청 · False 아님 · None 판단 못 함(모델·임베딩 없음)."""
    model = _load(path or MODEL)
    if model is None:
        return None
    try:
        if embed is None:
            import rag_search
            embed = rag_search.embed_query
        return probability(masked_question, embed, model) >= model[2]
    except Exception:
        return None
