"""LangGraph 문답 흐름 (서버·모델 없이 실행)."""
import unittest

import ontology_graph as og
import rag_graph as rg

PARTS = [
    {"lib_id": "A:x1", "library": "A", "name": "x1", "description": "", "keywords": "ldo regulator linear",
     "footprint": "", "datasheet": "", "extends": "", "pin_count": 3},
    {"lib_id": "A:x2", "library": "A", "name": "x2", "description": "", "keywords": "ldo regulator linear",
     "footprint": "", "datasheet": "", "extends": "", "pin_count": 3},
]
ONT = og.build_graph(PARTS, min_cooccurrence=2)


def hit(text, score):
    return {"text": text, "score": score, "filename": "f.pdf", "page": 1}


class Recorder:
    def __init__(self, by_query):
        self.by_query, self.queries, self.llm_calls, self.answers = by_query, [], [], []

    def search(self, q):
        self.queries.append(q)
        return self.by_query(q)

    def generate(self, question, context, feedback=""):
        self.llm_calls.append((question, context, feedback))
        return self.answers.pop(0) if self.answers else "답"


def run(rec, **kw):
    deps = rg.RagDeps(search=rec.search, generate=rec.generate, **kw)
    return rg.ask(rg.build_rag_graph(deps), "ldo 전압")


class RagGraphTest(unittest.TestCase):
    def test_parts_answer_short_circuits_everything(self):
        rec = Recorder(lambda q: [hit("t", 0.9)])
        out = run(rec, parts_answer=lambda q: "핀 표")
        self.assertEqual((out["answer"], out["answered_by"]), ("핀 표", "kicad-library"))
        self.assertEqual((rec.queries, rec.llm_calls), ([], []))

    def test_sufficient_evidence_goes_straight_to_generate(self):
        rec = Recorder(lambda q: [hit("근거", 0.8)])
        out = run(rec, min_score=0.5, ontology=ONT)
        self.assertEqual(rec.queries, ["ldo 전압"])
        self.assertFalse(out["low_confidence"])
        self.assertIn("[자료 1] (f.pdf · p.1) 근거", rec.llm_calls[0][1])
        self.assertEqual(rec.llm_calls[0][2], "")

    def test_weak_first_search_is_broadened_with_ontology_then_succeeds(self):
        rec = Recorder(lambda q: [hit("근거", 0.8 if "regulator" in q else 0.2)])
        out = run(rec, min_score=0.5, ontology=ONT)
        self.assertEqual(len(rec.queries), 2)
        self.assertIn("regulator", rec.queries[1])
        self.assertEqual(out["extra_terms"], ["linear", "regulator"])
        self.assertFalse(out["low_confidence"])

    def test_retry_is_bounded_and_marks_low_confidence(self):
        rec = Recorder(lambda q: [hit("약한 근거", 0.2)])
        out = run(rec, min_score=0.5, ontology=ONT, max_retries=1)
        self.assertEqual(len(rec.queries), 2)  # 무한 루프 없음
        self.assertTrue(out["low_confidence"])
        self.assertEqual(out["answered_by"], "llm")

    def test_no_expansion_means_no_retry(self):
        rec = Recorder(lambda q: [hit("약한 근거", 0.2)])
        out = run(rec, min_score=0.5, ontology=None)
        self.assertEqual(len(rec.queries), 1)
        self.assertTrue(out["low_confidence"])

    def test_no_sources_skips_the_model(self):
        rec = Recorder(lambda q: [])
        out = run(rec, min_score=0.5, ontology=ONT)
        self.assertEqual(out["answered_by"], "none")
        self.assertEqual(out["answer"], rg.NO_EVIDENCE_ANSWER)
        self.assertEqual(rec.llm_calls, [])

    def test_trace_records_each_step(self):
        rec = Recorder(lambda q: [hit("근거", 0.8 if "regulator" in q else 0.2)])
        out = run(rec, min_score=0.5, ontology=ONT)
        steps = [t.split(":")[0].split("#")[0] for t in out["trace"]]
        self.assertEqual(steps, ["parts_lookup", "retrieve", "grade", "broaden", "retrieve", "grade", "generate"])


class VerifyCiteTest(unittest.TestCase):
    SRC = [{"text": "예산은 88,123억 원으로 47% 늘었다", "score": 0.9, "filename": "f.pdf", "page": 3},
           {"text": "전혀 다른 내용의 문단입니다", "score": 0.8, "filename": "f.pdf", "page": 9}]

    def go(self, answers, **flags):
        rec = Recorder(lambda q: self.SRC)
        rec.answers = list(answers)
        deps = rg.RagDeps(search=rec.search, generate=rec.generate, **flags)
        return rec, rg.ask(rg.build_rag_graph(deps), "예산이 얼마나 늘었어")

    def test_flags_off_means_plain_generate(self):
        rec, out = self.go(["예산은 88,123억 원"])
        self.assertEqual(out["answer"], "예산은 88,123억 원")
        self.assertEqual(len(rec.llm_calls), 1)

    def test_verify_accepts_regeneration_only_when_fewer_ungrounded(self):
        rec, out = self.go(["예산은 77,777억 원", "예산은 88,123억 원으로 47% 늘었다"], verify=True)
        self.assertEqual(out["regenerated"], "accepted")
        self.assertIn("77777", rec.llm_calls[1][2])
        self.assertIn("88,123", out["answer"])

    def test_verify_rejects_regeneration_that_does_not_improve(self):
        rec, out = self.go(["예산은 77,777억 원", "예산은 88,888억 원"], verify=True)
        self.assertEqual(out["regenerated"], "rejected")
        self.assertIn("77,777", out["answer"])
        self.assertEqual(len(rec.llm_calls), 2)  # 한 번만 다시 쓴다

    def test_clean_answer_is_not_regenerated(self):
        rec, out = self.go(["예산은 88,123억 원으로 47% 늘었다"], verify=True)
        self.assertEqual(len(rec.llm_calls), 1)
        self.assertNotIn("regenerated", out)

    def test_cite_appends_when_missing(self):
        _, out = self.go(["예산은 88,123억 원으로 47% 늘었다"], cite=True)
        self.assertIn("근거: [자료 1] (f.pdf · p.3)", out["answer"])
        self.assertNotIn("[자료 2]", out["answer"])

    def test_cite_keeps_model_citation(self):
        _, out = self.go(["예산은 88,123억 원 [자료 1]"], cite=True)
        self.assertEqual(out["answer"], "예산은 88,123억 원 [자료 1]")


if __name__ == "__main__":
    unittest.main()
