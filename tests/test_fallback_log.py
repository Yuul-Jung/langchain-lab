"""안내 문구로 바뀌기 전 답 기록 (서버·모델 없이 실행)."""
import json
import tempfile
import unittest
from pathlib import Path

import fallback_log


class FallbackLogTest(unittest.TestCase):
    def test_record_appends_one_line_with_position_and_context(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "sub" / "fallback.jsonl"
            self.assertTrue(fallback_log.record("질문", "가나다 X 라마바", "고친 답", ["X"], "m", path))
            self.assertTrue(fallback_log.record("질문2", "abc", "", [], "m", path))
            lines = path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 2)
            first = json.loads(lines[0])
            self.assertEqual(first["draft"], "가나다 X 라마바")
            self.assertEqual(first["stray"][0]["first_at"], 4)
            self.assertIn("X", first["stray"][0]["context"])

    def test_failure_never_raises(self):
        with tempfile.TemporaryDirectory() as d:
            blocker = Path(d) / "file"
            blocker.write_text("x")
            self.assertFalse(fallback_log.record("q", "a", "b", [], "m", blocker / "x.jsonl"))

    def test_default_path_is_under_ignored_data_dir(self):
        self.assertEqual(fallback_log.DEFAULT_PATH.parts[-3:-1], ("data", "diagnostics"))


if __name__ == "__main__":
    unittest.main()
