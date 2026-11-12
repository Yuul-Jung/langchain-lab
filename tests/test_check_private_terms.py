"""올리기 전 낱말 대조 도구 (서버 없이 실행, 지어낸 자료 사용)."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "check_private_terms", Path(__file__).resolve().parent.parent / "scripts" / "check-private-terms.py")
tool = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(tool)


class CollectTermsTest(unittest.TestCase):
    def make(self, allow=None):
        folder = Path(tempfile.mkdtemp())
        rows = [{"id": "q1", "answer_keys": [["45,678"], ["Blue Folder", "블루 폴더"]], "keywords": ["가상낱말", "ab"]},
                {"id": "q2", "keywords": ["Python"]}]
        (folder / "questions.jsonl").write_text(
            "# 설명 줄\n" + "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n깨진 줄\n", encoding="utf-8")
        (folder / "keywords.txt").write_text("# 설명\n지어낸말\n\n", encoding="utf-8")
        if allow is not None:
            (folder / "allow-terms.txt").write_text(allow, encoding="utf-8")
        return folder

    def test_terms_come_from_answer_keys_keywords_and_the_keyword_list(self):
        terms = tool.collect_terms(self.make())
        self.assertEqual(terms, {"45,678", "Blue Folder", "블루 폴더", "가상낱말", "Python", "지어낸말"})   # 'ab' 는 3자 미만

    def test_allowed_terms_are_left_out(self):
        terms = tool.collect_terms(self.make(allow="# 흔한 낱말\npython\n"))
        self.assertNotIn("Python", terms)
        self.assertIn("가상낱말", terms)


class FindTermsTest(unittest.TestCase):
    def test_spacing_and_case_are_ignored(self):
        terms = {"Blue Folder", "45,678", "가상낱말"}
        self.assertEqual(tool.find_terms("예시는 blue  folder 에 넣고 값은 45,678 입니다", terms), ["45,678", "Blue Folder"])
        self.assertEqual(tool.find_terms("가상 낱말이 들어 있습니다", terms), ["가상낱말"])

    def test_short_english_terms_must_be_whole_words(self):
        self.assertEqual(tool.find_terms("Blog 를 엽니다. BLOG 글", {"LOG"}), [])
        self.assertEqual(tool.find_terms("LOG 묶음을 봅니다", {"LOG"}), ["LOG"])
        self.assertEqual(tool.find_terms("log는 7묶음", {"LOG"}), ["LOG"])           # 한글 조사가 붙어도 찾는다

    def test_english_terms_of_several_words_are_found_with_any_spacing(self):
        self.assertEqual(tool.find_terms("파일은 blue  folder 에, 또는 BlueFolder 에 둡니다", {"Blue Folder"}), ["Blue Folder"])
        self.assertEqual(tool.find_terms("BlueFolders 는 다른 이름입니다", {"Blue Folder"}), [])

    def test_embedded_images_are_ignored(self):
        html = '<img src="data:image/jpeg;base64,AAA+XK7/LOG+q9==" alt="그림"> 본문'
        self.assertEqual(tool.find_terms(html, {"XK7", "LOG"}), [])

    def test_clean_text_has_no_matches(self):
        self.assertEqual(tool.find_terms("지어낸 값 12,340 과 Sample Folder 만 씁니다", {"Blue Folder", "45,678"}), [])


class ParseStatusTest(unittest.TestCase):
    def test_current_names_are_listed_and_deleted_or_old_names_are_not(self):
        out = " M 작업일지.md\0A  tests/new_test.py\0R  docs/new name.html\0docs/old.html\0 D gone.py\0?? scripts/tool.py\0"
        self.assertEqual(tool.parse_status(out), ["작업일지.md", "tests/new_test.py", "docs/new name.html", "scripts/tool.py"])

    def test_empty_output_means_no_files(self):
        self.assertEqual(tool.parse_status(""), [])


if __name__ == "__main__":
    unittest.main()
