"""판단 정확도 계산 (서버·모델 없이 실행)."""
import importlib.util
import unittest
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "route_eval", Path(__file__).resolve().parent.parent / "scripts" / "run-route-eval.py")
route_eval = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(route_eval)


def hits(score, terms=("a",)):
    return [{"score": score, "matched_terms": list(terms), "source": "documents"}]


class SweepTest(unittest.TestCase):
    def test_missed_and_wrong_are_listed_per_threshold(self):
        rows = [("documents", "q1", hits(0.9)), ("documents", "q2", hits(0.7)),
                ("general", "g1", hits(0.8)), ("library", "l1", hits(0.9, terms=()))]
        r = {x["threshold"]: x for x in route_eval.sweep(rows, (0.75, 0.85))}
        self.assertEqual((r[0.75]["missed_documents"], r[0.75]["wrongly_documents"]), (["q2"], ["g1"]))
        self.assertEqual((r[0.85]["missed_documents"], r[0.85]["wrongly_documents"]), (["q2"], []))
        self.assertEqual((r[0.75]["n_documents"], r[0.75]["n_others"]), (2, 2))


if __name__ == "__main__":
    unittest.main()
