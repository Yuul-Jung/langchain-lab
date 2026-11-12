#!/usr/bin/env python3
"""평가 질문을 실제 채팅(RAG 모드)에 넣어 답변을 확인한다 — 문서·색인은 바꾸지 않는다.

run-eval.py 는 검색 단계(정답 쪽을 찾는가)만 본다. 이 스크립트는 그 다음 단계,
"채팅이 실제로 맞는 내용을 말하는가"를 기계적으로 확인한다.

질문 파일(data/eval/questions.jsonl)에 answer_keys 를 적어 둔 문항만 사실 포함 여부를 본다.
  "answer_keys": [["12,340"], ["27%", "27 %"]]
  - 바깥 목록의 모든 묶음이 답변에 있어야 한다. 묶음 안에서는 하나만 있으면 된다(표기가 여러 가지일 때).
  - 띄어쓰기와 대소문자는 무시한다.

확인하는 것:
  - 근거 포함: 채팅이 근거로 쓴 자료에 정답 문서의 정답 쪽이 있는가
  - 사실 포함: 답변에 answer_keys 가 들어 있는가
  - 인용: 답변에 [자료 N] 표시가 있는가
  - 대체 문구: 한국어 답변을 만들지 못해 안내 문구로 바뀌었는가
  - 외국 문자: 답변에 한자·가나·태국 문자 등이 섞였는가 (문서의 한자를 그대로 인용한 경우도 센다)
이것은 '핵심 낱말이 들어 있는가'를 보는 확인이지, 답변 전체가 옳은지 판정하는 것이 아니다.
틀린 설명 속에 맞는 숫자가 들어 있어도 '사실 포함'으로 센다.

출력에는 답변 본문을 넣지 않는다. 답변 전체는 data/eval/answer-results/ 에만 저장한다
(GitHub에 올라가지 않음).

사용:
  .venv/bin/python scripts/run-answer-eval.py            # 전체 (질문당 15~20초)
  .venv/bin/python scripts/run-answer-eval.py --limit 3  # 앞의 3문항만
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
QUESTIONS = ROOT / "data" / "eval" / "questions.jsonl"
RESULTS = ROOT / "data" / "eval" / "answer-results"   # run-eval.py 의 results/ 와 섞이지 않게
FALLBACK_MARK = "다른 언어가 혼용"
# 한국어 답변에 섞이면 안 되는 문자: 한자 · 일본어 가나 · 태국 문자 · 키릴 문자 · 아랍 문자 · 데바나가리
FOREIGN_SCRIPT = re.compile("[\u4e00-\u9fff\u3040-\u30ff\u0e00-\u0e7f\u0400-\u04ff\u0600-\u06ff\u0900-\u097f]")


def norm(text) -> str:
    """띄어쓰기와 대소문자를 무시하고 비교하기 위한 꼴."""
    return "".join(str(text).split()).lower()


def facts_present(answer: str, answer_keys) -> bool | None:
    """answer_keys 의 모든 묶음이 답변에 있는지. 키가 없으면 None(확인 안 함)."""
    if not answer_keys:
        return None
    flat = norm(answer)
    return all(any(norm(alt) in flat for alt in group) for group in answer_keys)


def score_answer(item: dict, response: dict, seconds: float) -> dict:
    """채팅 응답 하나를 확인한 결과 (답변 본문은 넣지 않는다)."""
    answer = str(response.get("answer") or "")
    pages = set(item["pages"])
    sources = response.get("sources") or []
    return {
        "id": item["id"],
        "evidence": any(s.get("document_id") == item["document_id"] and s.get("page") in pages for s in sources),
        "sources": len(sources),
        "facts": facts_present(answer, item.get("answer_keys")),
        "cited": bool(re.search(r"\[자료\s*\d+\]", answer)),
        "fallback": FALLBACK_MARK in answer,
        "foreign": len(FOREIGN_SCRIPT.findall(answer)),
        "rewrite": response.get("rewrite"),
        "chars": len(answer),
        "seconds": round(seconds, 1),
    }


def summarize(results: list[dict]) -> dict:
    n = len(results)
    with_keys = [r for r in results if r["facts"] is not None]
    return {
        "questions": n,
        "evidence": round(sum(r["evidence"] for r in results) / n, 3),
        "facts": round(sum(r["facts"] for r in with_keys) / len(with_keys), 3) if with_keys else None,
        "facts_checked": len(with_keys),
        "cited": round(sum(r["cited"] for r in results) / n, 3),
        "fallback": sum(r["fallback"] for r in results),
        "foreign_answers": sum(1 for r in results if r["foreign"]),
        "rewritten": sum(1 for r in results if r.get("rewrite") not in (None, "none")),
        "seconds_median": round(statistics.median(r["seconds"] for r in results), 1),
        "seconds_max": max(r["seconds"] for r in results),
    }


def main():
    import requests

    parser = argparse.ArgumentParser(description="평가 질문으로 채팅 답변 확인 (읽기 전용)")
    parser.add_argument("--questions", default=str(QUESTIONS))
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--limit", type=int, default=0, help="앞의 N문항만 (0 이면 전체)")
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--no-save", action="store_true")
    args = parser.parse_args()

    items = [json.loads(line) for line in Path(args.questions).read_text(encoding="utf-8").splitlines()
             if line.strip() and not line.lstrip().startswith("#")]
    if args.limit:
        items = items[:args.limit]
    try:
        known = [d["document_id"] for d in requests.get(args.base_url + "/api/documents", timeout=30).json()["documents"]]
    except Exception as exc:
        print("서버에서 문서 목록을 읽지 못했습니다:", exc)
        return 2
    results, answers = [], {}
    print(f"{'id':6s} 근거 포함  사실 포함  인용  대체 문구  외국 문자  시간")
    for item in items:
        matches = [d for d in known if d.startswith(item["document_id"])]
        if len(matches) != 1:
            print(f"{item['id']:6s} 문서를 찾지 못해 건너뜀")
            continue
        item = dict(item, document_id=matches[0])
        started = time.time()
        try:
            r = requests.post(args.base_url + "/api/chat", timeout=args.timeout,
                              json={"mode": "rag", "messages": [{"role": "user", "content": item["question"]}]})
            r.raise_for_status()
            response = r.json()
        except Exception as exc:
            print(f"{item['id']:6s} 요청 실패: {type(exc).__name__}")
            continue
        row = score_answer(item, response, time.time() - started)
        results.append(row)
        answers[item["id"]] = {"answer": response.get("answer"), "model": response.get("model"),
                               "sources": [{k: s.get(k) for k in ("document_id", "page", "score")}
                                           for s in response.get("sources") or []]}
        mark = lambda v: "-" if v is None else ("예" if v else "아니오")
        print(f"{row['id']:6s} {mark(row['evidence']):9s} {mark(row['facts']):9s} {mark(row['cited']):5s} "
              f"{mark(row['fallback']):9s} {row['foreign']:5d}자   {row['seconds']:5.1f}초")
    if not results:
        print("확인한 문항이 없습니다.")
        return 2
    summary = summarize(results)
    print("\n요약:", json.dumps(summary, ensure_ascii=False))
    print("주의: '사실 포함'은 핵심 낱말이 답변에 있는지만 봅니다. 답변 전체의 옳고 그름을 판정하지 않습니다.")
    if not args.no_save:
        RESULTS.mkdir(parents=True, exist_ok=True)
        out = RESULTS / f"answers-{datetime.now():%Y%m%d-%H%M%S}.json"
        out.write_text(json.dumps({"summary": summary, "results": results, "answers": answers},
                                  ensure_ascii=False, indent=1), encoding="utf-8")
        print("결과 저장(답변 본문 포함, 내 PC 전용):", out.relative_to(ROOT))
    print("안전: 문서·색인을 바꾸지 않았고 답변 본문은 출력하지 않았습니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
