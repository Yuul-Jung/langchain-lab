"""온톨로지 개념 승인 화면(/ontology)의 데이터와 저장.

개념마다 근거를 한곳에 모아 보여 주고, 사람이 승인·보류·반려를 누르면 data/ontology/approvals.jsonl 에 한 줄을 덧붙인다.
- 시드(static_data/ontology_ko_en_seed.json)는 바꾸지 않는다. 같은 개념이 여러 줄이면 마지막 줄이 이긴다
  (ontology_graph.apply_approvals 와 같은 규칙). 그래서 사람의 클릭은 앞선 위임 승인을 덮어쓴다.
- 기록: approver = "human: 사용자 (승인 화면)", 날짜·시각, 이유(선택), 직전 줄의 위험 용어 표시를 이어받는다.
- 화면은 저장만 한다. 그래프 반영은 scripts/build-ontology-ko.py 실행(서버는 graph_ko.json 이 바뀌면 다음 질문 때 다시 읽음, 재시작 불필요). 화면에 '반영 대기' 수 표시.
- 근거 파일(검토 시트·독립 검토)이 없어도 화면은 시드만으로 동작한다. 접근 제어는 app.py 의 access_guard 가 맡는다.
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
SEED = ROOT / "static_data" / "ontology_ko_en_seed.json"
ONTO = ROOT / "data" / "ontology"
APPROVALS = ONTO / "approvals.jsonl"
HUMAN = "human: 사용자 (승인 화면)"
DECISIONS = ("approved", "proposed", "rejected")   # 승인 · 보류(승인 전으로 되돌림) · 반려

router = APIRouter(prefix="/api/ontology")


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
                continue          # 깨진 줄 하나 때문에 화면 전체를 멈추지 않는다
    return rows


def _by_index(rows: list[dict]) -> dict[int, dict]:
    return {r["index"]: r for r in rows if isinstance(r.get("index"), int)}


def latest_decisions(rows: list[dict]) -> dict[int, dict]:
    """개념 번호 → 마지막 결정 줄(머리말 줄 제외)."""
    out: dict[int, dict] = {}
    for r in rows:
        if "decision" in r and isinstance(r.get("index"), int):
            out[r["index"]] = r
    return out


def concepts(onto_dir: Path = ONTO, seed_path: Path = SEED) -> dict:
    entries = json.loads(seed_path.read_text(encoding="utf-8"))["entries"]
    sheet = _by_index(_jsonl(onto_dir / "review_sheet.jsonl"))
    peer1 = _by_index(_jsonl(onto_dir / "review_peer.jsonl"))
    peer2 = _by_index(_jsonl(onto_dir / "review_peer_r2.jsonl"))
    rows = _jsonl(onto_dir / "approvals.jsonl")
    latest = latest_decisions(rows)
    built = (onto_dir / "graph_ko.json").stat().st_mtime if (onto_dir / "graph_ko.json").exists() else 0
    items = []
    for i, e in enumerate(entries):
        s, p1, p2, d = sheet.get(i, {}), peer1.get(i, {}), peer2.get(i, {}), latest.get(i)
        items.append({
            "index": i, "ko": e.get("ko", []), "kw": e.get("kw", []),
            "lib": e.get("lib", []) + [x + "*" for x in e.get("lib_prefix", [])],
            "evidence_parts": s.get("evidence_parts"), "example_parts": s.get("example_parts", []),
            "wikidata_supported_terms": s.get("wikidata_supported_terms"),
            "auto": {"recommendation": s.get("recommendation"), "flags": s.get("flags", []),
                     "fix_proposal": s.get("fix_proposal")},
            "peer": {"verdict": p2.get("verdict") or p1.get("verdict"),
                     "reason": p1.get("reason") if p2.get("reason") in (None, "1차와 같음") else p2.get("reason"),
                     "wrong_terms": p1.get("wrong_terms", []), "risky_terms": p1.get("risky_terms", []),
                     "missing_synonyms": p1.get("missing_synonyms", [])},
            "status": d.get("decision") if d else "proposed",
            "by": d.get("approver") if d else None, "at": d.get("date") if d else None,
            "note": d.get("reason") if d else None,
        })
    pending = sum(1 for r in rows if str(r.get("approver", "")).startswith("human:") and _row_time(r) > built)
    counts = {k: sum(1 for x in items if x["status"] == k) for k in DECISIONS}
    return {"concepts": items, "counts": counts, "human_decisions": sum(1 for r in rows if str(r.get("approver", "")).startswith("human:")),
            "pending_rebuild": pending}


def _row_time(r: dict) -> float:
    try:
        return datetime.fromisoformat(r.get("time") or r.get("date") or "").timestamp()
    except ValueError:
        return 0.0


def record(index: int, decision: str, note: str = "", onto_dir: Path = ONTO, seed_path: Path = SEED,
           now: Optional[datetime] = None) -> dict:
    """사람의 결정을 한 줄 덧붙인다. 번호가 시드에 없거나 결정 값이 틀리면 ValueError."""
    if decision not in DECISIONS:
        raise ValueError("결정은 approved · proposed · rejected 중 하나여야 합니다.")
    entries = json.loads(seed_path.read_text(encoding="utf-8"))["entries"]
    if not 0 <= index < len(entries):
        raise ValueError("없는 개념 번호입니다.")
    path = onto_dir / "approvals.jsonl"
    prev = latest_decisions(_jsonl(path)).get(index, {})
    now = now or datetime.now()
    row = {"index": index, "ko": entries[index]["ko"][0], "decision": decision, "approver": HUMAN,
           "date": now.date().isoformat(), "time": now.isoformat(timespec="seconds"),
           "reason": note.strip()[:300] or "사람이 승인 화면에서 결정", "round": "human",
           "risky_terms": prev.get("risky_terms", []), "previous": prev.get("decision", "proposed")}
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:      # 덧붙이기만 한다(이전 기록은 남는다)
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)
    return row


class Decision(BaseModel):
    index: int = Field(ge=0)
    decision: str
    note: str = Field(default="", max_length=300)


@router.get("/concepts")
def api_concepts():
    try:
        return concepts()
    except Exception:
        raise HTTPException(status_code=500, detail="개념 목록을 읽지 못했습니다.")


@router.post("/decision")
def api_decision(body: Decision):
    try:
        row = record(body.index, body.decision, body.note)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"saved": row}
