import unittest
from unittest import mock

import query_translate as qt
import settings


class QueryTranslateTest(unittest.TestCase):
    def test_content_words_drop_function_words_and_duplicates(self):
        self.assertEqual(qt.content_words("What's the maximum rise time in I2C fast mode? Rise"),
                         ["maximum", "rise", "time", "I2C", "fast", "mode"])
        self.assertEqual(qt.content_words(None), [])

    def test_missing_model_returns_none(self):
        with mock.patch.dict(qt._state, {}, clear=True), mock.patch.dict(qt._cache, {}, clear=True), \
             mock.patch.object(settings, "DOCUMENT_TRANSLATE_MODEL", "/nonexistent/model"):
            self.assertIsNone(qt.translate("질문"))
            self.assertIn("loaded", qt._state)

    def test_off_by_default(self):
        self.assertEqual(settings.DOCUMENT_QUERY_TRANSLATE, "off")



class HangulRatioTest(unittest.TestCase):
    def test_ratio(self):
        import document_pipeline as dp
        self.assertEqual(dp.hangul_ratio(""), 0.0)
        self.assertLess(dp.hangul_ratio("Rise time of SDA and SCL"), 0.2)
        self.assertGreater(dp.hangul_ratio("상승 시간은 SDA 기준"), 0.5)


if __name__ == "__main__":
    unittest.main()
