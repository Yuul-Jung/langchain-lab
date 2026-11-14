import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

import datasheet_review as dr

# 지어낸 후보(실제 데이터시트 아님)
C = [{"doc": "x.pdf", "field": "supply_max_v", "value": 5.5, "page": 3, "quote": "VCC 4.5 5.5 V"},
     {"doc": "x.pdf", "field": "abs_max_supply_v", "value": 7.0, "page": 2, "quote": "VCC -0.5 7 V"},
     {"doc": "y.pdf", "field": "temp_max_c", "value": 85.0, "page": 1, "quote": "TA -40 85 C"}]


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name)
        (self.d / "candidates.jsonl").write_text("\n".join(json.dumps(c) for c in C) + "\n", encoding="utf-8")
        self.k = [dr.key_of(c["doc"], c["field"], c["value"], c["page"]) for c in C]

    def tearDown(self):
        self.tmp.cleanup()


class Items(Base):
    def test_extractor_value_is_not_in_pending_items(self):
        its = dr.items(self.d)
        self.assertEqual(len(its), 3)
        self.assertTrue(all("value" not in i and i["decision"] is None and i["status"] == "대기" for i in its))
        self.assertTrue(next(i for i in its if i["field"] == "abs_max_supply_v")["human_only"])

    def test_decided_item_reveals_extractor_value(self):
        dr.record(self.k[0], 5.5, directory=self.d)
        i = next(i for i in dr.items(self.d) if i["key"] == self.k[0])
        self.assertEqual((i["status"], i["decision"]["outcome"], i["decision"]["extracted_value"]), ("결정됨", "confirmed", 5.5))


class Record(Base):
    def test_outcomes(self):
        self.assertEqual(dr.record(self.k[0], 5.5, directory=self.d)["outcome"], "confirmed")
        self.assertEqual(dr.record(self.k[0], 6.0, directory=self.d)["outcome"], "disputed")   # 마지막 줄이 이김
        self.assertEqual(dr.record(self.k[2], None, directory=self.d)["outcome"], "unclear")

    def test_appends_only_and_rejects_bad_input(self):
        dr.record(self.k[0], 5.5, directory=self.d)
        dr.record(self.k[0], 5.5, directory=self.d)
        self.assertEqual(len((self.d / "decisions.jsonl").read_text(encoding="utf-8").splitlines()), 2)
        with self.assertRaises(ValueError):
            dr.record("none|x|1|1", 1.0, directory=self.d)
        with self.assertRaises(ValueError):
            dr.record(self.k[0], 5.5, approver="누군가", directory=self.d)


class Confirmed(Base):
    def test_human_confirmation_becomes_datasheet_without_tier(self):
        dr.record(self.k[0], 5.5, directory=self.d)
        ev = dr.confirmed_evidence(self.d)["x.pdf"]["values"]["supply_max_v"][0]
        self.assertEqual((ev["source"], ev["value"], "tier" in ev), ("datasheet", 5.5, False))

    def test_delegated_confirmation_has_tier(self):
        dr.record(self.k[0], 5.5, approver="delegated: jung-29 + 71", directory=self.d)
        ev = dr.confirmed_evidence(self.d)["x.pdf"]["values"]["supply_max_v"][0]
        self.assertEqual(ev["tier"], "delegated")

    def test_abs_max_needs_a_human(self):
        dr.record(self.k[1], 7.0, approver="delegated: jung-29 + 71", directory=self.d)
        self.assertEqual(dr.confirmed_evidence(self.d), {})                       # 위임 확인은 넘기지 않음
        dr.record(self.k[1], 7.0, directory=self.d)                               # 사람 확인
        self.assertIn("abs_max_supply_v", dr.confirmed_evidence(self.d)["x.pdf"]["values"])

    def test_unclear_and_disputed_use_reviewers_own_value_only(self):
        dr.record(self.k[2], None, directory=self.d)
        self.assertEqual(dr.confirmed_evidence(self.d), {})
        dr.record(self.k[0], 4.9, directory=self.d)                               # 검토자가 직접 읽은 값
        self.assertEqual(dr.confirmed_evidence(self.d)["x.pdf"]["values"]["supply_max_v"][0]["value"], 4.9)

    def test_feeds_constraints_with_a_warning_for_delegated(self):
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "eda_harness"))
        from edaharness import constraints as cs
        dr.record(self.k[0], 5.5, approver="delegated: jung-29 + 71", directory=self.d)
        rec = dr.confirmed_evidence(self.d)["x.pdf"]
        f = cs.check_operating_point(rec, 3.3)
        self.assertIn("DELEGATED_CONFIRMATION", [x["code"] for x in f if x["field"] == "supply_max_v"])


class Api(unittest.TestCase):
    def test_bad_decision_is_400_without_internal_detail(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        app = FastAPI()
        app.include_router(dr.router)
        r = TestClient(app).post("/api/datasheet-review/decision", json={"key": "none|x|1|1", "value": 1})
        self.assertEqual(r.status_code, 400)
        self.assertNotIn("/", r.json()["detail"])


if __name__ == "__main__":
    unittest.main()
