#!/usr/bin/env python3
"""한·영 다리 2·3단계: 캐낸 영어 구절(bridge_candidates.jsonl)에 한국어 후보를 붙이고 자동으로 확인한다.

2단계 제안: 로컬 LLM(LM Studio, 기본 deepseek-r1-distill-qwen-14b)에 25개씩 묶어 '데이터시트에서 쓰는 한국어 표기'를 받는다(오프라인 일괄).
3단계 자동 확인(기준은 결과를 보기 전에 고정, 2026-11-14):
  - 되돌림: 한국어를 opus-mt-ko-en 으로 다시 영어로 → 원래 구절 낱말과 겹치는 비율 ≥ 0.5
  - 임베딩: qwen3-embedding 으로 한국어·영어 유사도(코사인) ≥ 0.6
  둘 다 만족 → auto '권고 승인', 아니면 '보류'. 한글이 없거나 비면 '수정 필요'.
출력: data/ontology/bridge_phrases.jsonl — 모두 review_status 'proposed'(승인은 위임 2단계 검토를 거친다). 이어서 하기(--resume) 지원.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
IN = ROOT / "data" / "ontology" / "bridge_candidates.jsonl"
OUT = ROOT / "data" / "ontology" / "bridge_phrases.jsonl"
MIN_OVERLAP, MIN_COS = 0.5, 0.6
PROMPT = ("다음은 전자 부품 데이터시트와 KiCad 부품 설명에 나오는 영어 용어입니다. 한국 엔지니어가 데이터시트를 읽을 때 쓰는 "
          "가장 흔한 한국어 표기를 하나씩 주세요. 영어 약어를 그대로 쓰는 것이 더 흔하면 영어 그대로 두세요. "
          "JSON 객체 하나만 출력하세요. 키는 영어 용어 그대로, 값은 한국어 표기.\n\n")


def ask_llm(phrases: list[str], model: str, url: str) -> dict:
    import settings
    r = requests.post(f"{url}/chat/completions", timeout=900, json={
        "model": model, "temperature": 0, "max_tokens": 4000,
        "messages": [{"role": "user", "content": PROMPT + "\n".join(phrases)}]})
    r.raise_for_status()
    text = re.sub(r"<think>.*?</think>", "", r.json()["choices"][0]["message"]["content"], flags=re.S)
    m = re.search(r"\{.*\}", text, re.S)
    try:
        data = json.loads(m.group(0)) if m else {}
    except ValueError:
        data = {}
    return {k.strip().lower(): str(v).strip() for k, v in data.items() if isinstance(k, str)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", type=int, default=25)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--model", default="deepseek-r1-distill-qwen-14b")
    args = ap.parse_args()
    import settings, rag_search, query_translate
    import numpy as np
    cands = [json.loads(l) for l in IN.read_text(encoding="utf-8").splitlines() if l.strip()]
    if args.limit:
        cands = cands[:args.limit]
    done = {}
    if args.resume and OUT.exists():
        done = {json.loads(l)["en"]: json.loads(l) for l in OUT.read_text(encoding="utf-8").splitlines() if l.strip()}
    todo = [c for c in cands if c["en"] not in done]
    t0 = time.time()
    with OUT.open("a" if args.resume else "w", encoding="utf-8") as f:
        for i in range(0, len(todo), args.batch):
            chunk = todo[i:i + args.batch]
            try:
                ko = ask_llm([c["en"] for c in chunk], args.model, settings.LM_STUDIO_URL)
            except Exception as exc:
                print("LLM 실패, 이 묶음은 건너뜀:", type(exc).__name__); continue
            for c in chunk:
                k = ko.get(c["en"], "")
                row = {**c, "ko": k, "source": f"llm:{args.model}", "review_status": "proposed"}
                if not re.search(r"[가-힣]", k):
                    row.update(auto="수정 필요" if not k or k.lower() != c["en"] else "영어 그대로", back_en="", overlap=0.0, cos=0.0)
                else:
                    back = query_translate.translate(k) or ""
                    words = set(c["en"].replace("-", " ").split())
                    got = set(re.findall(r"[a-z]+", back.lower()))
                    overlap = len(words & got) / len(words) if words else 0.0
                    try:
                        a, b = np.array(rag_search.embed_query(k)), np.array(rag_search.embed_query(c["en"]))
                        cos = float(a @ b / (np.linalg.norm(a) * np.linalg.norm(b)))
                    except Exception:
                        cos = 0.0
                    row.update(back_en=back, overlap=round(overlap, 2), cos=round(cos, 3),
                               auto="권고 승인" if overlap >= MIN_OVERLAP and cos >= MIN_COS else "보류")
                f.write(json.dumps(row, ensure_ascii=False) + "\n"); f.flush()
            print(f"{min(i + args.batch, len(todo))}/{len(todo)} · {time.time() - t0:.0f}초", flush=True)


if __name__ == "__main__":
    main()
