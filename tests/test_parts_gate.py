import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

import parts_gate as gate

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("train_gate", ROOT / "scripts" / "train-parts-gate.py")
train = importlib.util.module_from_spec(spec)
spec.loader.exec_module(train)


def model_file(d, w=(1.0, 0.0), b=0.0, tau=0.2):
    p = Path(d) / "model.npz"
    np.savez(p, w=np.array(w), b=b, tau=tau)
    return p


class Veto(unittest.TestCase):
    def setUp(self):
        gate._cache.clear()
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def test_vetoes_only_below_threshold(self):
        p = model_file(self.tmp.name, w=(5.0, 0.0), tau=0.2)
        self.assertTrue(gate.veto("부품 아님", embed=lambda q: [-1.0, 0.0], path=p))    # 확률 ≈ 0.007
        self.assertFalse(gate.veto("부품", embed=lambda q: [1.0, 0.0], path=p))         # 확률 ≈ 0.993
        self.assertFalse(gate.veto("애매함", embed=lambda q: [0.0, 1.0], path=p))       # 확률 0.5

    def test_missing_model_or_failing_embed_never_vetoes(self):
        self.assertFalse(gate.veto("질문", embed=lambda q: [-1.0, 0.0], path=Path(self.tmp.name) / "none.npz"))
        p = model_file(self.tmp.name)
        def boom(q):
            raise RuntimeError("LM 꺼짐")
        self.assertFalse(gate.veto("질문", embed=boom, path=p))
        self.assertFalse(gate.veto("질문", embed=lambda q: [1.0, 0.0, 0.0], path=p))     # 차원 다름

    def test_setting_off_disables(self):
        p = model_file(self.tmp.name, w=(5.0, 0.0))
        with mock.patch.object(gate.settings, "PARTS_GATE_ML", False, create=True):
            self.assertFalse(gate.veto("부품 아님", embed=lambda q: [-1.0, 0.0], path=p))


class Training(unittest.TestCase):
    def test_threshold_rejects_no_parts_in_cv(self):
        rng = np.random.default_rng(1)
        X = np.vstack([rng.normal(1, 0.3, (40, 4)), rng.normal(-1, 0.3, (40, 4))])
        X /= np.linalg.norm(X, axis=1, keepdims=True)
        y = np.array([1] * 40 + [0] * 40)
        cv_p = train.cv_probabilities(X, y)
        tau = train.threshold(cv_p, y)
        self.assertEqual(int((cv_p[y == 1] < tau).sum()), 0)
        self.assertGreater(int((cv_p[y == 0] < tau).sum()), 0)


if __name__ == "__main__":
    unittest.main()
