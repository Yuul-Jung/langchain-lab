"""부품 경로가 질문마다 어떻게 판단했는지를 이 PC에만 남긴다 — 실제 사용 질문으로 검증하기 위한 재료.

저장 위치: data/diagnostics/parts_route.jsonl — data/ 는 GitHub에 올라가지 않는다.
**기록에는 사용자가 입력한 질문 원문이 들어 있다(문서 질문 포함). 외부로 보내거나 공유하지 않는다.**
기록에 실패해도 채팅은 영향받지 않는다. 끄려면 PARTS_ROUTE_LOG=false.
"""
from __future__ import annotations

import json
import secrets
import sys
from datetime import datetime
from pathlib import Path

DEFAULT_PATH = Path(__file__).resolve().parent / "data" / "diagnostics" / "parts_route.jsonl"
# 질문 원문이 쌓이므로 상한을 둔다: 파일이 MAX_BYTES 를 넘으면 가장 최근 KEEP_ENTRIES 건만 남기고 나머지는 지운다
MAX_BYTES = 1_000_000
KEEP_ENTRIES = 1000


def in_server_process() -> bool:
    """웹 서버(uvicorn) 안에서 실행 중일 때만 True. 평가·조사 스크립트가 app 을 불러 써도 uvicorn 은 불러오지 않으므로
    그 트래픽은 설정(.env 가 환경변수보다 먼저 읽힘)과 상관없이 구조적으로 기록되지 않는다."""
    return "uvicorn" in sys.modules


FEEDBACK_LABELS = {
    "correct": "맞음",                        # 부품 답이 맞았다
    "not_parts": "부품 질문 아님",            # 부품 질문이 아닌데 부품으로 답했다(오처리)
    "wrong_parts": "다른 부품을 원함",        # 부품 질문은 맞지만 결과가 틀렸다
    "missed_parts": "부품을 물었는데 못 알아들음",   # 부품 질문인데 일반·문서 답으로 갔다(놓침)
}


def new_id() -> str:
    return secrets.token_hex(6)


def entry(question: str, state: dict, entry_id: str | None = None) -> dict:
    parts = state.get("parts") or []
    anchor = state.get("anchor") or {}
    return {"id": entry_id or new_id(), "time": datetime.now().isoformat(timespec="seconds"), "question": question,
            "handled": bool(state.get("answered")), "concepts": state.get("concepts", []),
            "backend": state.get("backend"), "anchor": anchor.get("lib_id"),
            "libraries": sorted({p.get("library") or str(p.get("lib_id", "")).split(":")[0] for p in parts}),
            "trace": [t[:80] for t in state.get("trace", [])]}


def record(question: str, state: dict, path: Path | None = None) -> str | None:
    """한 건을 덧붙여 쓰고 그 기록 번호(id)를 돌려준다. 실패하면 None (예외를 밖으로 내지 않는다)."""
    row = entry(question, state)
    return row["id"] if _append(row, path) else None


def feedback(entry_id: str, label: str, path: Path | None = None) -> bool:
    """사용자가 답 아래 버튼으로 남긴 평가 한 건(기록 번호와 라벨만, 질문 원문은 다시 쓰지 않는다)."""
    if label not in FEEDBACK_LABELS or not entry_id:
        return False
    return _append({"type": "feedback", "ref": entry_id, "label": label,
                    "time": datetime.now().isoformat(timespec="seconds")}, path)


def _append(row: dict, path: Path | None) -> bool:
    try:
        path = path or DEFAULT_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        if path.stat().st_size > MAX_BYTES:
            _trim(path)
        return True
    except Exception:
        return False


def _trim(path: Path) -> None:
    """가장 최근 KEEP_ENTRIES 건만 남긴다(임시 파일에 쓰고 바꿔치기해서 중간에 끊겨도 기록이 깨지지 않게)."""
    lines = path.read_text(encoding="utf-8").splitlines()[-KEEP_ENTRIES:]
    tmp = path.with_suffix(".tmp")
    tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    tmp.replace(path)


def read(path: Path | None = None) -> list[dict]:
    path = path or DEFAULT_PATH
    if not path.is_file():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out
