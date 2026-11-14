#!/usr/bin/env python3
"""부품 경로 사용 기록(data/diagnostics/parts_route.jsonl)을 요약한다 — 읽기 전용.
기본은 건수만 보인다. 질문 원문은 --show 를 줄 때만 보인다(이 PC 전용 기록, 공유 금지).
사용: .venv/bin/python scripts/parts-route-report.py [--show handled|unhandled|all] [--limit 30]"""
from __future__ import annotations
import argparse, re, sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import parts_graph as pg, parts_log  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--show", choices=["handled", "unhandled", "all"], default=None)
    ap.add_argument("--limit", type=int, default=30)
    args = ap.parse_args()
    rows = parts_log.read()
    if not rows:
        print("기록이 없습니다 (data/diagnostics/parts_route.jsonl). 채팅에서 질문을 보내면 쌓입니다.")
        return 0
    handled = [r for r in rows if r["handled"]]
    per_day = Counter(r["time"][:10] for r in rows)
    print(f"전체 {len(rows)}건 | 부품 경로가 처리 {len(handled)}건 ({len(handled)/len(rows):.0%}) | 처리 안 함 {len(rows)-len(handled)}건")
    print("날짜별:", dict(sorted(per_day.items())))
    print("검색 방식:", dict(Counter(r.get("backend") or "-" for r in handled)))
    print("자주 나온 개념:", Counter(c for r in handled for c in r.get("concepts", [])).most_common(8))
    print("자주 나온 분류:", Counter(l for r in handled for l in r.get("libraries", [])).most_common(8))
    # 놓쳤을 가능성이 있는 질문: 처리하지 않았지만 부품을 찾는 말이 든 것(건수만; 원문은 --show)
    maybe = [r for r in rows if not r["handled"] and pg.INTENT.search(r["question"]) and not pg.EXPLAIN.search(r["question"])
             and not pg.NONPART.search(r["question"]) and not pg.DOC_WORDS.search(r["question"])]
    print(f"처리 안 했지만 부품을 찾는 말이 든 질문(놓쳤을 가능성) {len(maybe)}건")
    if args.show:
        pick = {"handled": handled, "unhandled": maybe, "all": rows}[args.show][-args.limit:]
        for r in pick:
            print(f"  [{r['time'][5:16]}] {'처리' if r['handled'] else '미처리'} {r['question'][:80]}  → {r.get('concepts') or r.get('anchor') or ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
