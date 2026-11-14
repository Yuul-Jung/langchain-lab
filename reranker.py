"""문서 검색 후보 재순위(교차 인코더) — 한국어 질문과 영어 데이터시트 청크를 함께 읽고 점수를 매긴다.

- 설정 DOCUMENT_RERANKER (기본 꺼짐). 켜도 모델·라이브러리가 없거나 실패하면 원래 순서를 그대로 쓴다(조용한 대체).
- 모델: settings.DOCUMENT_RERANKER_MODEL (로컬 경로, 기본 data/tools/models/mmarco-mMiniLMv2-L12-H384-v1, Apache-2.0).
  내려받은 모델은 data/ 아래라 커밋되지 않는다. 필요한 라이브러리는 requirements-rerank.txt(선택 설치, CPU).
- 라이브러리는 처음 쓸 때만 불러온다(꺼져 있으면 메모리를 쓰지 않는다).
- dev(데이터시트 16문항)에서 상위 20개 재순위: hit@1 0.375→0.688, MRR 0.489→0.719, CPU 지연 중앙값 0.87초.
"""
from __future__ import annotations

import math
import threading

import settings

_lock = threading.Lock()
_state: dict = {}


def _load():
    """(tokenizer, model) 또는 실패 시 None. 실패는 한 번만 시도한다(매 질문마다 다시 불러오지 않게)."""
    with _lock:
        if "loaded" in _state:
            return _state.get("model")
        _state["loaded"] = True
        try:
            import torch  # noqa: F401
            from transformers import AutoModelForSequenceClassification, AutoTokenizer
            path = settings.DOCUMENT_RERANKER_MODEL
            tok = AutoTokenizer.from_pretrained(path)
            mod = AutoModelForSequenceClassification.from_pretrained(path).eval()
            _state["model"] = (tok, mod)
        except Exception:
            _state["model"] = None
        return _state["model"]


def _scores(query: str, texts: list[str], model) -> list[float]:
    import torch
    tok, mod = model
    with torch.no_grad():
        enc = tok([query] * len(texts), texts, padding=True, truncation=True, max_length=384, return_tensors="pt")
        return mod(**enc).logits.view(-1).tolist()


def rerank(query: str, hits: list[dict], pool: int | None = None, scorer=None) -> list[dict]:
    """상위 pool 개를 교차 인코더 점수로 다시 정렬한다. 점수는 0~1(시그모이드)로 바꿔 score 에 넣고
    원래 점수는 pre_rerank_score 에 남긴다(점수 폭 컷오프가 같은 척도로 동작하게). 실패하면 hits 그대로."""
    pool = pool or settings.DOCUMENT_RERANKER_POOL
    head, tail = hits[:pool], hits[pool:]
    if len(head) < 2:
        return hits
    try:
        if scorer is None:
            model = _load()
            if model is None:
                return hits
            raw = _scores(query, [h.get("text", "") for h in head], model)
        else:
            raw = scorer(query, [h.get("text", "") for h in head])
        if len(raw) != len(head):
            return hits
    except Exception:
        return hits
    scored = [{**h, "pre_rerank_score": h.get("score"), "score": round(1 / (1 + math.exp(-s)), 4)}
              for h, s in zip(head, raw)]
    scored.sort(key=lambda h: -h["score"])
    floor = scored[-1]["score"]
    # 재순위하지 않은 나머지는 재순위된 것보다 앞에 오지 않게 맨 아래 점수 밑으로 둔다
    return scored + [{**h, "pre_rerank_score": h.get("score"), "score": round(max(0.0, floor - 0.001 * (i + 1)), 4)}
                     for i, h in enumerate(tail)]
