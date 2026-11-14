"""답이 안내 문구로 바뀌었거나(fallback) 못 고친 채 그대로 보여 줬을 때(kept), 원래 답을 이 PC에만 남긴다.

목적: 무엇이 섞여서(어떤 글자가, 몇 개, 어디에) 안내 문구로 바뀌었는지 나중에 알아보기 위함.
저장 위치: data/diagnostics/fallback.jsonl — data/ 는 GitHub에 올라가지 않는다.
기록에는 질문과 답 본문이 들어 있으므로 외부로 보내거나 공유하지 않는다.
기록에 실패해도 채팅은 영향받지 않는다.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

DEFAULT_PATH = Path(__file__).resolve().parent / "data" / "diagnostics" / "fallback.jsonl"
CONTEXT = 12   # 섞인 글자 앞뒤로 보여 줄 글자 수


def stray_positions(answer: str, stray_chars: list[str]) -> list[dict]:
    """섞인 글자마다 위치와 앞뒤 문맥 (본문 전체를 열지 않고도 어디에 섞였는지 보게 한다)."""
    out = []
    for ch in stray_chars:
        i = answer.find(ch)
        out.append({"char": ch, "count": answer.count(ch), "first_at": i,
                    "context": answer[max(0, i - CONTEXT): i + CONTEXT + 1]})
    return out


def record(question: str, draft: str, rewrite: str, stray_chars: list[str], model: str,
           path: Path | None = None, outcome: str = "fallback") -> bool:
    """한 건을 덧붙여 쓴다. 실패하면 False (예외를 밖으로 내지 않는다)."""
    try:
        path = path or DEFAULT_PATH      # 호출할 때 정한다(시험에서 DEFAULT_PATH 를 바꿀 수 있게)
        path.parent.mkdir(parents=True, exist_ok=True)
        entry = {"time": datetime.now().isoformat(timespec="seconds"), "model": model,
                 "outcome": outcome, "question": question, "draft": draft, "rewrite": rewrite,
                 "stray": stray_positions(draft, stray_chars),
                 "stray_after_rewrite": len(stray_chars) if stray_chars else 0}
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return True
    except Exception:
        return False
