"""데이터시트 값 확인 화면(/datasheet-review)의 데이터와 저장.

자동 추출한 값(datasheet_evidence, 출처 'extracted')은 사람이 인용문과 쪽수를 보고 확인해야 제약 판정에 쓸 수 있다.
- 확인하는 사람은 인용문·쪽수를 보고 **자기 값을 먼저 입력**한다(추출기의 값은 입력 뒤에 공개) — 도장만 찍는 확인이 되지 않게.
  인용문 안에 숫자가 들어 있으므로 값을 가리는 것은 완전한 눈가림이 아니라 '직접 읽게 하는' 장치다.
- 결정은 data/datasheet_review/decisions.jsonl 에 한 줄씩 덧붙인다(이전 기록은 남고 같은 항목은 마지막 줄이 이김).
- 확인한 사람 표시는 둘로 나뉜다: "human: …"(사용자가 화면에서) / "delegated: …"(두 세션 위임). 위임 확인은 사람 등급을 받지 못한다.
- 제약 모듈에 넘기는 값(confirmed_evidence):
    · 사람이 확인한 값 → source "datasheet"
    · 위임 확인 값 → source "datasheet", tier "delegated" (제약 판정에 경고가 남음)
    · **절대 최대 전원(abs_max_supply_v)은 사람 확인만 인정** — 설계의 기준이 되는 한계라서 위임 확인은 넘기지 않는다
- 후보·결정 파일은 data/ 아래(git 밖)이며 데이터시트 인용문이 들어 있어 공유·커밋하지 않는다.
"""
from __future__ import annotations

import fcntl
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent
DIR = ROOT / "data" / "datasheet_review"
CANDIDATES = DIR / "candidates.jsonl"
DECISIONS = DIR / "decisions.jsonl"
HUMAN = "human: 사용자 (확인 화면)"
FIELD_LABEL = {"supply_min_v": "권장 전원 최소(V)", "supply_max_v": "권장 전원 최대(V)",
               "abs_max_supply_v": "절대 최대 전원(V)", "temp_min_c": "동작 온도 최소(°C)", "temp_max_c": "동작 온도 최대(°C)"}
HUMAN_ONLY = {"abs_max_supply_v"}          # 위임 확인으로 올릴 수 없는 필드
TOL = 1e-6

router = APIRouter(prefix="/api/datasheet-review")


def key_of(doc: str, field: str, value: float, page: int) -> str:
    return f"{doc}|{field}|{value:g}|{page}"


def _jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def latest(rows: list[dict]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for r in rows:
        if isinstance(r.get("key"), str):
            out[r["key"]] = r
    return out


def items(directory: Path = DIR) -> list[dict]:
    """확인 대기·완료 목록. 추출기의 값(value)은 넣지 않는다 — 결정 뒤에만 공개."""
    cands = _jsonl(directory / "candidates.jsonl")
    dec = latest(_jsonl(directory / "decisions.jsonl"))
    out = []
    for c in cands:
        k = key_of(c["doc"], c["field"], c["value"], c["page"])
        d = dec.get(k)
        out.append({"key": k, "doc": c["doc"], "field": c["field"], "label": FIELD_LABEL.get(c["field"], c["field"]),
                    "page": c["page"], "quote": c["quote"], "human_only": c["field"] in HUMAN_ONLY,
                    "status": ("결정됨" if d else "대기"),
                    "decision": ({"outcome": d["outcome"], "approver": d["approver"], "at": d.get("time"),
                                  "reviewer_value": d.get("reviewer_value"), "extracted_value": c["value"]} if d else None)})
    return out


def record(key: str, reviewer_value: Optional[float], note: str = "", approver: str = HUMAN,
           directory: Path = DIR, now: Optional[datetime] = None) -> dict:
    """결정을 한 줄 덧붙인다. reviewer_value=None 은 '인용문에서 이 값을 확인할 수 없음'."""
    cands = {key_of(c["doc"], c["field"], c["value"], c["page"]): c for c in _jsonl(directory / "candidates.jsonl")}
    c = cands.get(key)
    if c is None:
        raise ValueError("없는 항목입니다.")
    if not (approver.startswith("human:") or approver.startswith("delegated:")):
        raise ValueError("확인한 사람 표시는 human: 또는 delegated: 로 시작해야 합니다.")
    if reviewer_value is None:
        outcome = "unclear"
    elif abs(float(reviewer_value) - c["value"]) <= TOL * max(1.0, abs(c["value"])):
        outcome = "confirmed"
    else:
        outcome = "disputed"
    now = now or datetime.now()
    row = {"key": key, "doc": c["doc"], "field": c["field"], "page": c["page"], "extracted_value": c["value"],
           "reviewer_value": reviewer_value, "outcome": outcome, "approver": approver,
           "time": now.isoformat(timespec="seconds"), "note": note.strip()[:300]}
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / "decisions.jsonl").open("a", encoding="utf-8") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)
    return {"outcome": outcome, "extracted_value": c["value"], "reviewer_value": reviewer_value}


def confirmed_evidence(directory: Path = DIR) -> dict[str, dict]:
    """문서 → 제약 모듈 입력 {"values": {필드: [{"value","source":"datasheet","ref","page","tier"?}]}}.

    사람이 확인한 값과 위임 확인 값만. 의견이 갈린(disputed) 항목은 검토자가 직접 읽은 값을 쓴다(같은 등급 규칙).
    확인 못 함(unclear)은 넘기지 않는다. 절대 최대 전원은 위임 확인이면 넘기지 않는다."""
    out: dict[str, dict] = {}
    for d in latest(_jsonl(directory / "decisions.jsonl")).values():
        if d["outcome"] == "unclear" or d.get("reviewer_value") is None:
            continue
        human = str(d["approver"]).startswith("human:")
        if d["field"] in HUMAN_ONLY and not human:
            continue
        ev = {"value": float(d["reviewer_value"]), "source": "datasheet", "ref": d["doc"], "page": d["page"]}
        if not human:
            ev["tier"] = "delegated"
        out.setdefault(d["doc"], {"values": {}})["values"].setdefault(d["field"], []).append(ev)
    return out


class Decision(BaseModel):
    key: str = Field(min_length=1, max_length=300)
    value: Optional[float] = None
    note: str = Field(default="", max_length=300)


@router.get("/items")
def api_items():
    try:
        its = items()
    except Exception:
        raise HTTPException(status_code=500, detail="목록을 읽지 못했습니다.")
    return {"items": its, "pending": sum(1 for i in its if i["status"] == "대기")}


@router.post("/decision")
def api_decision(body: Decision):
    try:
        return record(body.key, body.value, body.note)          # 화면에서 누르면 항상 사람 등급
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
