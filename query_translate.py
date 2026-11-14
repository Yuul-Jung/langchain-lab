"""한국어 질문 → 영어 번역 (영어 데이터시트 검색 보강용). 설정 DOCUMENT_QUERY_TRANSLATE (기본 off).

- 모델: Helsinki-NLP/opus-mt-ko-en (Apache-2.0, 약 300MB), 로컬 경로 settings.DOCUMENT_TRANSLATE_MODEL.
  CPU 에서 질문 하나 약 0.14초(2026-11-14 측정). transformers + sentencepiece 가 필요하다(requirements-rerank.txt 와 같은 선택 설치).
- 처음 쓸 때만 불러오고, 실패하면 None 을 돌려준다(검색은 원래 질문만으로 계속).
- 쓰는 곳: document_pipeline.search_uploaded — 'lexical' 은 번역 낱말을 낱말 후보·재순위에만, 'dual' 은 번역문 임베딩으로도 후보를 찾는다.
"""
from __future__ import annotations

import re
import threading

import settings

_lock = threading.Lock()
_state: dict = {}
_cache: dict[str, str | None] = {}
CACHE_MAX = 512

# 번역문에서 낱말 검색에 쓰지 않을 영어 기능어(낱말 후보가 'the'·'how' 로 넘치지 않게)
EN_STOP = {"the", "a", "an", "is", "are", "was", "be", "do", "does", "did", "how", "what", "what's", "whats", "which", "who",
           "when", "where", "why", "of", "in", "on", "at", "to", "for", "from", "with", "by", "and", "or", "it", "its",
           "this", "that", "there", "you", "we", "i", "my", "your", "can", "use", "used", "much", "many", "long", "if",
           "have", "has", "go", "goes", "into", "about", "kind", "happens", "work", "works", "get", "me"}


def _load():
    with _lock:
        if "loaded" in _state:
            return _state.get("model")
        _state["loaded"] = True
        try:
            import torch
            from transformers import MarianMTModel, MarianTokenizer
            torch.set_num_threads(min(4, torch.get_num_threads()))   # 4개면 충분(0.16초), 다른 작업과 CPU 를 다투지 않게
            path = settings.DOCUMENT_TRANSLATE_MODEL
            _state["model"] = (MarianTokenizer.from_pretrained(path), MarianMTModel.from_pretrained(path).eval())
        except Exception:
            _state["model"] = None
        return _state["model"]


def translate(question: str) -> str | None:
    """영어 번역문 또는 None(모델 없음·실패). 같은 질문은 캐시."""
    if question in _cache:
        return _cache[question]
    model = _load()
    if model is None:
        return None
    try:
        import torch
        tok, mod = model
        with torch.no_grad():
            out = mod.generate(**tok([question[:400]], return_tensors="pt"), max_new_tokens=48, num_beams=2)
        text = tok.decode(out[0], skip_special_tokens=True).strip() or None
    except Exception:
        text = None
    if len(_cache) >= CACHE_MAX:
        _cache.clear()
    _cache[question] = text
    return text


def content_words(english: str | None) -> list[str]:
    """번역문에서 낱말 검색에 쓸 내용어(기능어 제외, 2글자 이상, 중복 제거)."""
    out: list[str] = []
    for w in re.findall(r"[A-Za-z0-9][A-Za-z0-9\-]*", english or ""):
        if len(w) >= 2 and w.lower() not in EN_STOP and w.lower() not in (x.lower() for x in out):
            out.append(w)
    return out
