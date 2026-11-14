"""한자 → 한글 음 변환 (서버·모델 없이 실행)."""
import importlib.util
import json
import unittest
from pathlib import Path

import hanja_ko as h

_spec = importlib.util.spec_from_file_location(
    "build_hanja", Path(__file__).resolve().parent.parent / "scripts" / "build-hanja-table.py")
build_hanja = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(build_hanja)


def conv(text, allowed=""):
    return h.to_hangul(text, allowed)[0]


class ConvertTest(unittest.TestCase):
    def test_hanja_after_hangul_keeps_base_sound(self):
        self.assertEqual(conv("답案을 쓰세요"), "답안을 쓰세요")
        self.assertEqual(conv("남女"), "남녀")

    def test_initial_sound_law_only_at_word_start(self):
        self.assertEqual(conv("力學"), "역학")
        self.assertEqual(conv("女性 論理"), "여성 논리")
        self.assertEqual(conv("(來日)"), "(내일)")
        self.assertEqual(conv("노力"), "노력")

    def test_ryeol_ryul_after_open_syllable(self):
        self.assertEqual(conv("序列"), "서열")
        self.assertEqual(conv("分裂"), "분열")
        self.assertEqual(conv("法律"), "법률")

    def test_known_words_not_used_to_build_the_rules(self):
        for word, expected in [("學校", "학교"), ("大學", "대학"), ("電子", "전자"), ("信號", "신호"),
                               ("回路", "회로"), ("電壓", "전압"), ("理論", "이론"), ("勞動", "노동"),
                               ("料理", "요리"), ("流動", "유동")]:
            self.assertEqual(conv(word), expected, word)

    def test_ambiguous_characters_are_left_alone(self):
        table = h.load_table()
        for ch in "樂行說切":
            self.assertNotIn(ch, table, ch)
        text, n, left = h.to_hangul("樂기")
        self.assertEqual((text, n, left), ("樂기", 0, ["樂"]))

    def test_allowed_characters_are_quotations_and_stay(self):
        self.assertEqual(conv("案은 인용", allowed="案"), "案은 인용")

    def test_text_without_hanja_is_unchanged(self):
        s = "한국어 문장 abc 123 [자료 1] **굵게**"
        self.assertEqual(h.to_hangul(s), (s, 0, []))


class InitialSoundLawTest(unittest.TestCase):
    def test_rules(self):
        for old, new in [("녀", "여"), ("뉴", "유"), ("니", "이"), ("랴", "야"), ("려", "여"), ("례", "예"),
                         ("료", "요"), ("류", "유"), ("리", "이"), ("라", "나"), ("래", "내"), ("로", "노"),
                         ("뢰", "뇌"), ("루", "누"), ("르", "느"), ("론", "논"), ("가", "가"), ("나", "나")]:
            self.assertEqual(h.initial_sound_law(old), new, old)


class BuildTest(unittest.TestCase):
    def test_pick_reading(self):
        self.assertEqual(build_hanja.pick_reading("안:0E"), "안")
        self.assertEqual(build_hanja.pick_reading("력:0E 역:0"), "력")          # 두음법칙 차이뿐
        self.assertIsNone(build_hanja.pick_reading("항:0N 행:0E"))              # 정말 다른 음
        self.assertIsNone(build_hanja.pick_reading("낙:0 락:0E 악:0N 요:0N"))

    def test_table_file_is_well_formed_and_has_source(self):
        data = json.loads(h.TABLE_PATH.read_text(encoding="utf-8"))
        self.assertIn("Unicode", data["license"])
        self.assertGreater(len(data["chars"]), 5000)
        self.assertTrue(all(len(k) == 1 and len(v) == 1 for k, v in data["chars"].items()))


if __name__ == "__main__":
    unittest.main()
