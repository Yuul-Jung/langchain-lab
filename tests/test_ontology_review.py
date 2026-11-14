import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from fastapi.testclient import TestClient

import ontology_review as orv

# 지어낸 시드·근거·승인 기록 (네트워크·서버 없음)
SEED = {"entries": [{"ko": ["가젯 알파", "알파"], "kw": ["alpha"], "lib": ["Lib_A"]},
                    {"ko": ["가젯 베타"], "kw": [], "lib": [], "lib_prefix": ["Lib_B"]}]}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        self.seed = d / "seed.json"
        self.seed.write_text(json.dumps(SEED, ensure_ascii=False), encoding="utf-8")
        self.onto = d / "onto"
        self.onto.mkdir()
        w = lambda name, rows: (self.onto / name).write_text(
            "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
        w("review_sheet.jsonl", [{"index": 0, "recommendation": "권고 승인", "flags": [], "evidence_parts": 12,
                                  "example_parts": ["Lib_A:X1"]},
                                 {"index": 1, "recommendation": "보류", "flags": ["근거 부품 적음"]}])
        w("review_peer.jsonl", [{"_note": "머리말"}, {"index": 0, "verdict": "OK", "reason": "맞음", "wrong_terms": [],
                                                       "risky_terms": ["알파"], "missing_synonyms": []},
                                {"index": 1, "verdict": "의심", "reason": "넓음", "wrong_terms": [], "risky_terms": [],
                                 "missing_synonyms": ["베타칩"]}])
        w("approvals.jsonl", [{"_note": "머리말"}, {"index": 0, "ko": "가젯 알파", "decision": "approved",
                                                     "approver": "delegated: test", "date": "2026-01-01",
                                                     "risky_terms": ["알파"]}])

    def tearDown(self):
        self.tmp.cleanup()


class Concepts(Base):
    def test_merges_sources_and_latest_decision(self):
        got = orv.concepts(self.onto, self.seed)
        a, b = got["concepts"]
        self.assertEqual(a["status"], "approved")
        self.assertTrue(a["by"].startswith("delegated"))
        self.assertEqual(a["auto"]["recommendation"], "권고 승인")
        self.assertEqual(a["peer"]["risky_terms"], ["알파"])
        self.assertEqual(b["status"], "proposed")
        self.assertEqual(b["lib"], ["Lib_B*"])
        self.assertEqual(got["counts"], {"approved": 1, "proposed": 1, "rejected": 0})

    def test_works_with_seed_only(self):
        empty = Path(self.tmp.name) / "empty"
        empty.mkdir()
        got = orv.concepts(empty, self.seed)
        self.assertEqual([c["status"] for c in got["concepts"]], ["proposed", "proposed"])


class Record(Base):
    def test_human_row_overrides_and_keeps_history(self):
        row = orv.record(0, "rejected", "  틀림  ", self.onto, self.seed, now=datetime(2026, 2, 1, 9, 0))
        self.assertEqual(row["approver"], orv.HUMAN)
        self.assertEqual(row["ko"], "가젯 알파")              # apply_approvals 의 짝 확인용 대표 용어
        self.assertEqual(row["previous"], "approved")
        self.assertEqual(row["risky_terms"], ["알파"])       # 위험 표시는 이어받음
        self.assertEqual(row["reason"], "틀림")
        lines = (self.onto / "approvals.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 3)                      # 덧붙이기만
        got = orv.concepts(self.onto, self.seed)
        self.assertEqual(got["concepts"][0]["status"], "rejected")
        self.assertEqual(got["human_decisions"], 1)
        self.assertEqual(got["pending_rebuild"], 1)          # 그래프 파일이 없으므로 반영 대기

    def test_rejects_bad_input(self):
        with self.assertRaises(ValueError):
            orv.record(5, "approved", "", self.onto, self.seed)
        with self.assertRaises(ValueError):
            orv.record(0, "approve", "", self.onto, self.seed)

    def test_note_is_trimmed_and_defaulted(self):
        row = orv.record(1, "approved", "", self.onto, self.seed)
        self.assertTrue(row["reason"])
        self.assertLessEqual(len(orv.record(1, "approved", "x" * 999, self.onto, self.seed)["reason"]), 300)


class Api(unittest.TestCase):
    def test_bad_decision_is_400_without_internal_detail(self):
        from fastapi import FastAPI
        app = FastAPI()
        app.include_router(orv.router)
        c = TestClient(app)
        r = c.post("/api/ontology/decision", json={"index": 0, "decision": "nope"})
        self.assertEqual(r.status_code, 400)
        self.assertNotIn("/", r.json()["detail"])


if __name__ == "__main__":
    unittest.main()
