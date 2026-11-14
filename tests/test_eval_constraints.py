import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("eval_constraints", ROOT / "scripts" / "eval-constraints.py")
ec = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ec)

# 지어낸 부품 값(실제 부품 아님)
GOLD = {"X:A": {"values": {"supply_min_v": [{"value": 3.0, "source": "datasheet"}],
                           "supply_max_v": [{"value": 5.0, "source": "datasheet"}],
                           "abs_max_supply_v": [{"value": 6.0, "source": "datasheet"}]}}}


def pred(**over):
    v = {f: [{"value": e[0]["value"], "source": "distributor"}] for f, e in GOLD["X:A"]["values"].items()}
    for k, x in over.items():
        v[k] = x
    return {"X:A": {"values": v}}


class EvalConstraints(unittest.TestCase):
    def test_identical_values_are_perfect(self):
        r = ec.evaluate(GOLD, pred())
        self.assertEqual((r["violation_recall"], r["violation_precision"], r["dangerous_pass"]), (1.0, 1.0, 0))

    def test_too_generous_limit_gives_dangerous_pass(self):
        r = ec.evaluate(GOLD, pred(abs_max_supply_v=[{"value": 30.0, "source": "distributor"}],
                                   supply_max_v=[{"value": 30.0, "source": "distributor"}]))
        self.assertGreater(r["dangerous_pass"], 0)

    def test_too_strict_limit_gives_false_alarm(self):
        r = ec.evaluate(GOLD, pred(supply_max_v=[{"value": 4.0, "source": "distributor"}]))   # 더 엄격한 상한만
        self.assertGreater(r["fp"], 0)
        self.assertEqual(r["dangerous_pass"], 0)

    def test_missing_record_is_blocked_not_pass(self):
        r = ec.evaluate(GOLD, {})
        self.assertEqual(r["dangerous_pass"], 0)
        self.assertEqual(r["blocked"], r["points"])


if __name__ == "__main__":
    unittest.main()
