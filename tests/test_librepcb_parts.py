"""LibrePCB 라이브러리 변환 (서버·네트워크 없이 합성 라이브러리로 실행)."""
import tempfile
import unittest
from pathlib import Path

import librepcb_parts as lp


def write(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


CMP = '''(librepcb_component C1
 (name "Op Amp")
 (name (locale "de") "Operationsverstärker")
 (description "dual")
 (category CAT2)
 (signal S1 (name "IN+") (role input) (required false))
 (signal S2 (name "OUT") (role output) (required false))
 (signal S3 (name "V+") (role power) (required false))
)'''
PKG = '''(librepcb_package P1
 (name "SOIC-8")
 (pad PAD1 (name "1"))
 (pad PAD2 (name "2"))
 (pad PAD10 (name "10"))
 (pad PAD3 (name "3"))
)'''
DEV = '''(librepcb_device D1
 (name "XYZ123")
 (description "My part")
 (keywords "opamp, dual")
 (category CAT2)
 (deprecated false)
 (resource "Datasheet" (mediatype "application/pdf") (url "https://example.invalid/x.pdf"))
 (component C1)
 (package P1)
 (pad PAD1 (optional false) (signal S1))
 (pad PAD2 (optional false) (signal S2))
 (pad PAD10 (optional true) (signal none))
 (pad PAD3 (optional false) (signal S3))
 (part "XYZ123-ABC" (manufacturer "Acme"))
 (part "XYZ123-DEF" (manufacturer "Acme"))
)'''
CAT1 = '(librepcb_component_category CAT1 (name "ICs") (name (locale "de") "ICs-de") (parent 00000000))'
CAT2 = '(librepcb_component_category CAT2 (name "Amplifiers") (parent CAT1))'


class LibraryTest(unittest.TestCase):
    def build(self, device_text=DEV, split=True):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        base, vendor = root / "Base.lplib", root / "Vendor.lplib"
        write(base / "cmp/C1/component.lp", CMP)
        write(base / "pkg/P1/package.lp", PKG)
        write(base / "cmpcat/CAT1/component_category.lp", CAT1)
        write(base / "cmpcat/CAT2/component_category.lp", CAT2)
        write(vendor / "dev/D1/device.lp", device_text)      # 장치는 다른 라이브러리의 컴포넌트·패키지를 참조한다
        lib = lp.Library()
        lib.add_library(base)
        lib.add_library(vendor, commit="abc123")
        return lib

    def test_device_resolves_component_and_package_from_another_library(self):
        entries, report = self.build().build()
        e = entries[0]
        self.assertEqual((e["library"], e["name"], e["component"], e["package"]), ("Vendor", "XYZ123", "Op Amp", "SOIC-8"))
        self.assertEqual((report["missing_component"], report["missing_package"], report["pads_unresolved"]), (0, 0, 0))
        self.assertEqual(e["repo_commit"], "abc123")

    def test_pins_use_package_pad_names_and_signal_roles_in_natural_order(self):
        e = self.build().build()[0][0]
        self.assertEqual([p["number"] for p in e["pins"]], ["1", "2", "3", "10"])    # 10 이 3 뒤에 온다
        self.assertEqual(e["pins"][0], {"number": "1", "name": "IN+", "role": "input"})

    def test_signal_none_means_unconnected_not_an_unresolved_reference(self):
        entries, report = self.build().build()
        pad10 = entries[0]["pins"][-1]
        self.assertEqual((pad10["number"], pad10["name"], pad10["role"]), ("10", "", "unconnected"))
        self.assertEqual(report["pads_unresolved"], 0)

    def test_locale_names_are_skipped_and_category_path_follows_parents(self):
        e = self.build().build()[0][0]
        self.assertEqual(e["category"], "ICs > Amplifiers")
        self.assertEqual(self.build().components["C1"]["name"], "Op Amp")      # (name (locale "de") ...) 가 아님

    def test_manufacturer_part_numbers_datasheets_keywords(self):
        e = self.build().build()[0][0]
        self.assertEqual((e["manufacturers"], e["mpns"]), (["Acme"], ["XYZ123-ABC", "XYZ123-DEF"]))
        self.assertEqual(e["datasheets"], ["https://example.invalid/x.pdf"])
        self.assertEqual(e["keywords"], ["opamp", "dual"])
        self.assertEqual((e["review_status"], e["license"]), ("proposed", "CC0-1.0"))

    def test_dangling_references_are_reported_not_hidden(self):
        broken = DEV.replace("(component C1)", "(component NOPE)").replace("(package P1)", "(package GONE)")
        entries, report = self.build(broken).build()
        self.assertEqual((report["missing_component"], report["missing_package"]), (1, 1))
        self.assertEqual(entries[0]["pin_count"], 4)                  # 항목은 남기되 핀 번호는 '?' 로 표시
        self.assertEqual(entries[0]["pins"][0]["number"], "?")

    def test_unreadable_file_is_recorded_and_others_still_load(self):
        lib = self.build()
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        bad = Path(tmp.name) / "Bad.lplib"
        write(bad / "dev/X/device.lp", "(librepcb_device X (name \"unclosed\"")
        write(bad / "dev/Y/device.lp", DEV.replace("D1", "Y"))
        lib.add_library(bad)
        entries, report = lib.build()
        self.assertEqual(report["read_errors"], 1)
        self.assertEqual(len(entries), 2)

    def test_deprecated_flag(self):
        entries, report = self.build(DEV.replace("(deprecated false)", "(deprecated true)")).build()
        self.assertTrue(entries[0]["deprecated"])
        self.assertEqual(report["deprecated"], 1)


if __name__ == "__main__":
    unittest.main()


class ExtraCatalogTest(unittest.TestCase):
    """KiCad 카탈로그에 LibrePCB 추가분을 이어 붙이는 부분 (임시 파일 사용)."""

    def setUp(self):
        import json
        import kicad_parts
        self.kp = kicad_parts
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / "catalog.jsonl"

        def entry(name, pins=2, deprecated=False, role="passive"):
            return {"library": "Vendor", "name": name, "description": "d", "keywords": ["k"], "package": "PKG",
                    "datasheets": ["https://example.invalid/d.pdf"], "pin_count": pins, "deprecated": deprecated,
                    "pins": [{"number": str(i + 1), "name": f"P{i + 1}", "role": role} for i in range(pins)],
                    "review_status": "proposed"}
        rows = [entry("QWX9000"), entry("NE555D"), entry("OLD7000", deprecated=True), entry("EMPTY1", pins=0)]
        self.path.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
        self.kicad = [{"lib_id": "Timer:NE555D", "library": "Timer", "name": "NE555D", "description": "", "keywords": "",
                       "footprint": "", "datasheet": "", "pin_count": 1, "pins": [{"number": "1", "name": "GND", "type": "power_in"}]}]

    def catalog(self, extras=True):
        from unittest import mock
        with mock.patch.object(self.kp, "EXTRA_CATALOG_PATH", self.path), \
             mock.patch.object(self.kp, "default_catalog", return_value=self.kicad):
            self.kp._extra_cache.clear()
            return self.kp.parts_catalog(extras)

    def test_adds_only_new_non_deprecated_devices_with_pins(self):
        names = [p["name"] for p in self.catalog()]
        self.assertEqual(names, ["NE555D", "QWX9000"])           # NE555D 는 KiCad 것만, 폐기·핀 없음 제외

    def test_can_be_switched_off(self):
        self.assertEqual([p["name"] for p in self.catalog(extras=False)], ["NE555D"])

    def test_answer_for_an_extra_part_warns_that_it_is_unverified_community_data(self):
        answer = self.kp.parts_answer("QWX9000 핀 정보", self.catalog())
        self.assertIn("LibrePCB", answer)
        self.assertIn("검증·승인 전", answer)
        self.assertIn("데이터시트로 확인", answer)

    def test_answer_for_a_kicad_part_is_unchanged_in_wording(self):
        self.assertIn("KiCad 공식 심볼 라이브러리", self.kp.parts_answer("NE555D 핀 정보", self.catalog()))

    def test_missing_extra_file_falls_back_to_kicad_only(self):
        from unittest import mock
        with mock.patch.object(self.kp, "EXTRA_CATALOG_PATH", self.path.parent / "none.jsonl"), \
             mock.patch.object(self.kp, "default_catalog", return_value=self.kicad):
            self.assertEqual(len(self.kp.parts_catalog()), 1)


class PhraseNameTest(unittest.TestCase):
    """이름에 띄어쓰기가 있는 부품을 이름 전체로 찾기."""

    def part(self, name, pins=2):
        return {"lib_id": f"X:{name}", "library": "X", "name": name, "description": "", "keywords": "",
                "footprint": "", "datasheet": "", "pin_count": pins,
                "pins": [{"number": str(i + 1), "name": f"P{i + 1}", "type": "passive"} for i in range(pins)]}

    def setUp(self):
        import kicad_parts
        self.kp = kicad_parts
        self.cat = [self.part("Arduino Nano V3", 3), self.part("Arduino Nano V3 Every", 4),
                    self.part("Big Board", 2), self.part("Old 7", 2), self.part("NE555D", 8)]

    def test_multiword_name_in_the_question_is_found_and_longest_match_wins(self):
        self.assertEqual(self.kp.part_tokens("Arduino Nano V3 Every 핀 정보", self.cat), ["Arduino Nano V3 Every"])
        self.assertIn("Arduino Nano V3 Every", self.kp.parts_answer("Arduino Nano V3 Every 핀 정보", self.cat))
        self.assertIn("**Arduino Nano V3**", self.kp.parts_answer("arduino nano v3 핀 정보", self.cat))   # 대소문자·띄어쓰기 무시

    def test_names_without_a_digit_or_too_short_are_not_matched(self):
        self.assertEqual(self.kp.part_tokens("Big Board 핀 정보", self.cat), [])      # 숫자 없음
        self.assertEqual(self.kp.part_tokens("Old 7 핀 정보", self.cat), [])          # 정규화하면 5자 (8자 미만)

    def test_needs_a_pin_word(self):
        self.assertEqual(self.kp.part_tokens("Arduino Nano V3 가 뭐야?", self.cat), [])

    def test_part_number_token_path_still_wins_and_phrase_path_is_not_tried(self):
        self.assertEqual(self.kp.part_tokens("NE555D 핀 정보", self.cat), ["NE555D"])


class MissingCatalogTest(unittest.TestCase):
    """카탈로그 파일이 없는 PC(새 PC·CI)에서도 채팅이 오류 없이 빈 목록으로 동작해야 한다."""

    def test_default_catalog_returns_an_empty_list_when_the_file_is_missing_even_on_the_first_call(self):
        from unittest import mock
        import kicad_parts
        with tempfile.TemporaryDirectory() as tmp, \
             mock.patch.object(kicad_parts, "CATALOG_PATH", Path(tmp) / "none.jsonl"), \
             mock.patch.object(kicad_parts, "EXTRA_CATALOG_PATH", Path(tmp) / "none2.jsonl"), \
             mock.patch.object(kicad_parts, "_catalog_cache", {}):          # 처음 호출 상태
            self.assertEqual(kicad_parts.default_catalog(), [])
            self.assertEqual(kicad_parts.default_catalog(), [])            # 두 번째 호출도
            self.assertEqual(kicad_parts.parts_catalog(), [])
            self.assertIsNone(kicad_parts.parts_answer("NE555 핀 정보", kicad_parts.parts_catalog()))
