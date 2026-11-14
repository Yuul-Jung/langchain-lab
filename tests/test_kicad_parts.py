"""KiCad 부품 목록 읽기·검색·매핑 제안 (KiCad·서버 없이 실행)."""
import unittest

import kicad_parts as kp

SAMPLE = '''(kicad_symbol_lib (version 20241209)
	(symbol "BASE_IC"
		(property "Reference" "U" (at 0 0 0))
		(property "Value" "BASE_IC" (at 0 0 0))
		(property "Footprint" "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm" (at 0 0 0))
		(property "Datasheet" "https://example.com/base.pdf" (at 0 0 0))
		(property "Description" "Dual timer" (at 0 0 0))
		(property "ki_keywords" "timer oscillator" (at 0 0 0))
		(symbol "BASE_IC_0_1"
			(rectangle (start 0 0) (end 1 1)))
		(symbol "BASE_IC_1_1"
			(pin power_in line
				(at 0 0 0)
				(length 2.54)
				(name "VCC" (effects (font (size 1 1))))
				(number "8" (effects (font (size 1 1)))))
			(pin input line
				(at 0 0 0)
				(length 2.54)
				(hide yes)
				(name "TRIG" (effects (font (size 1 1))))
				(number "2" (effects (font (size 1 1)))))
		)
	)
	(symbol "DERIVED_IC"
		(extends "BASE_IC")
		(property "Reference" "U" (at 0 0 0))
		(property "Value" "DERIVED_IC" (at 0 0 0))
		(property "Footprint" "" (at 0 0 0))
		(property "Datasheet" "~" (at 0 0 0))
		(property "Description" "" (at 0 0 0))
	)
	(symbol "Conn_01x04"
		(property "Reference" "J" (at 0 0 0))
		(property "Value" "Conn_01x04" (at 0 0 0))
		(property "Footprint" "" (at 0 0 0))
		(property "Datasheet" "~" (at 0 0 0))
		(property "Description" "Generic connector, single row, 01x04" (at 0 0 0))
		(property "ki_keywords" "connector" (at 0 0 0))
		(symbol "Conn_01x04_1_1"
			(pin passive line (at 0 0 0) (length 5) (name "Pin_1" (effects (font (size 1 1)))) (number "1" (effects (font (size 1 1)))))
			(pin passive line (at 0 0 0) (length 5) (name "Pin_2" (effects (font (size 1 1)))) (number "2" (effects (font (size 1 1)))))
			(pin passive line (at 0 0 0) (length 5) (name "Pin_3" (effects (font (size 1 1)))) (number "3" (effects (font (size 1 1)))))
			(pin passive line (at 0 0 0) (length 5) (name "Pin_4" (effects (font (size 1 1)))) (number "4" (effects (font (size 1 1)))))
		)
	)
)
'''


class ParseTest(unittest.TestCase):
    def setUp(self):
        self.parts = {p["name"]: p for p in kp.parse_symbol_library(SAMPLE, "Timer")}

    def test_only_top_level_symbols_are_parts(self):
        self.assertEqual(set(self.parts), {"BASE_IC", "DERIVED_IC", "Conn_01x04"})

    def test_properties_and_pins(self):
        p = self.parts["BASE_IC"]
        self.assertEqual(p["lib_id"], "Timer:BASE_IC")
        self.assertEqual(p["footprint"], "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm")
        self.assertEqual(p["datasheet"], "https://example.com/base.pdf")
        self.assertEqual([(x["number"], x["name"]) for x in p["pins"]], [("8", "VCC"), ("2", "TRIG")])

    def test_hidden_pin_is_still_counted(self):
        self.assertEqual(self.parts["BASE_IC"]["pin_count"], 2)

    def test_extends_inherits_pins_footprint_and_datasheet(self):
        d = self.parts["DERIVED_IC"]
        self.assertEqual(d["pin_count"], 2)
        self.assertEqual(d["footprint"], "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm")
        self.assertEqual(d["datasheet"], "https://example.com/base.pdf")

    def test_tilde_datasheet_means_none(self):
        self.assertEqual(self.parts["Conn_01x04"]["datasheet"], "")


class SearchTest(unittest.TestCase):
    def setUp(self):
        self.parts = kp.parse_symbol_library(SAMPLE, "Timer")

    def test_name_match_ranks_first_and_all_words_required(self):
        names = [p["name"] for p in kp.search_parts(self.parts, "timer")]
        self.assertEqual(names[0], "BASE_IC")
        self.assertEqual(kp.search_parts(self.parts, "timer connector"), [])

    def test_empty_query_returns_nothing(self):
        self.assertEqual(kp.search_parts(self.parts, "  "), [])


class MappingTest(unittest.TestCase):
    def setUp(self):
        self.conn = {p["name"]: p for p in kp.parse_symbol_library(SAMPLE, "Connector_Generic")}["Conn_01x04"]
        self.module = {"name": "SENSOR-MODULE", "kind": "module",
                       "pins": [{"number": "1", "name": "VCC"}, {"number": "2", "name": "TRIG"},
                                {"number": "3", "name": "ECHO"}, {"number": "4", "name": "GND"}]}

    def test_proposal_is_never_approved_and_flags_unchecked_ratings(self):
        pr = kp.propose_mapping(self.module, self.conn, footprint="Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Vertical")
        self.assertEqual(pr["review_status"], "proposed")
        self.assertFalse(pr["checks"]["ratings_compared"])
        self.assertTrue(any("정격" in w for w in pr["warnings"]))

    def test_position_mapping_is_marked_weak(self):
        pr = kp.propose_mapping(self.module, self.conn, footprint="X:Y")
        self.assertEqual(pr["checks"]["pin_map_basis"], "position")
        self.assertTrue(any("번호 순서" in w for w in pr["warnings"]))
        self.assertEqual(pr["target"]["footprint_chosen_by"], "specified")

    def test_missing_footprint_is_reported_and_blocks_approval(self):
        pr = kp.propose_mapping(self.module, self.conn)
        self.assertFalse(pr["checks"]["footprint_present"])
        with self.assertRaises(ValueError):
            kp.approve_mapping(pr, "확인함")

    def test_pin_count_mismatch_is_reported(self):
        short = {**self.module, "pins": self.module["pins"][:3]}
        pr = kp.propose_mapping(short, self.conn, footprint="X:Y")
        self.assertFalse(pr["checks"]["pin_count_match"])
        self.assertIn("핀 수가 다름", pr["warnings"])

    def test_approval_needs_reason_and_unmapped_pins_block_it(self):
        pr = kp.propose_mapping(self.module, self.conn, footprint="X:Y")
        with self.assertRaises(ValueError):
            kp.approve_mapping(pr, "  ")
        ok = kp.approve_mapping(pr, "데이터시트 핀 배치 확인")
        self.assertEqual(ok["review_status"], "approved")
        self.assertEqual(pr["review_status"], "proposed")  # 원본은 바뀌지 않음
        short = {**self.module, "pins": self.module["pins"][:3]}
        bad = kp.propose_mapping({**short, "pins": short["pins"] + [{"number": "9", "name": "X"}]}, self.conn, footprint="X:Y")
        bad["pin_map"][0]["target"] = None
        with self.assertRaises(ValueError):
            kp.approve_mapping(bad, "확인함")

    def test_name_based_mapping_when_names_match(self):
        base = {p["name"]: p for p in kp.parse_symbol_library(SAMPLE, "Timer")}["BASE_IC"]
        src = {"name": "X", "pins": [{"number": "1", "name": "vcc"}, {"number": "2", "name": "Trig"}]}
        pr = kp.propose_mapping(src, base)
        self.assertEqual(pr["checks"]["pin_map_basis"], "name")
        self.assertEqual([(m["source"], m["target"]) for m in pr["pin_map"]], [("1", "8"), ("2", "2")])
        self.assertEqual(pr["target"]["footprint_chosen_by"], "candidate")


if __name__ == "__main__":
    unittest.main()


class EsBodyTest(unittest.TestCase):
    def test_empty_query_has_no_search_body(self):
        self.assertIsNone(kp.es_search_body(" , "))

    def test_every_word_is_required_and_name_substring_is_allowed(self):
        body = kp.es_search_body("Timer 555", 5)
        musts = body["query"]["bool"]["must"]
        self.assertEqual(len(musts), 2)
        self.assertEqual(musts[1]["bool"]["should"][1]["wildcard"]["name.lower"]["value"], "*555*")
        self.assertEqual(body["size"], 5)

    def test_wildcard_characters_cannot_be_injected(self):
        body = kp.es_search_body("a*b? c\\\\d")
        values = [m["bool"]["should"][1]["wildcard"]["name.lower"]["value"] for m in body["query"]["bool"]["must"]]
        self.assertEqual(values, ["*ab*", "*cd*"])

    def test_pins_are_not_indexed_as_fields(self):
        self.assertFalse(kp.es_index_body()["mappings"]["properties"]["pins"]["enabled"])

    def test_bulk_uses_library_id_as_document_id(self):
        parts = kp.parse_symbol_library(SAMPLE, "Timer")
        actions = list(kp.es_bulk_actions(parts))
        self.assertEqual({a["_id"] for a in actions}, {"Timer:BASE_IC", "Timer:DERIVED_IC", "Timer:Conn_01x04"})
        self.assertTrue(all(a["_index"] == kp.ES_PARTS_INDEX for a in actions))


NE_SAMPLE = '''(kicad_symbol_lib (version 20241209)
	(symbol "NE555D"
		(property "Reference" "U" (at 0 0 0))
		(property "Footprint" "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm" (at 0 0 0))
		(property "Datasheet" "http://example.com/ne555.pdf" (at 0 0 0))
		(symbol "NE555D_1_1"
			(pin power_in line (at 0 0 0) (length 2) (name "GND" (effects (font (size 1 1)))) (number "1" (effects (font (size 1 1)))))
			(pin power_in line (at 0 0 0) (length 2) (name "VCC" (effects (font (size 1 1)))) (number "8" (effects (font (size 1 1)))))
			(pin input line (at 0 0 0) (length 2) (name "~{RST}" (effects (font (size 1 1)))) (number "4" (effects (font (size 1 1)))))
			(pin output line (at 0 0 0) (length 2) (name "OUT" (effects (font (size 1 1)))) (number "3" (effects (font (size 1 1)))))
		)
	)
	(symbol "NE555P"
		(property "Reference" "U" (at 0 0 0))
		(property "Footprint" "Package_DIP:DIP-8_W7.62mm" (at 0 0 0))
		(symbol "NE555P_1_1"
			(pin power_in line (at 0 0 0) (length 2) (name "GND" (effects (font (size 1 1)))) (number "1" (effects (font (size 1 1)))))
			(pin power_in line (at 0 0 0) (length 2) (name "VCC" (effects (font (size 1 1)))) (number "8" (effects (font (size 1 1)))))
			(pin input line (at 0 0 0) (length 2) (name "~{RST}" (effects (font (size 1 1)))) (number "4" (effects (font (size 1 1)))))
			(pin output line (at 0 0 0) (length 2) (name "OUT" (effects (font (size 1 1)))) (number "3" (effects (font (size 1 1)))))
		)
	)
)
'''


class PartsAnswerTest(unittest.TestCase):
    def setUp(self):
        self.parts = kp.parse_symbol_library(NE_SAMPLE, "Timer")

    def test_pin_question_with_known_part_gets_sorted_table(self):
        a = kp.parts_answer("NE555 IC 핀별 정보", self.parts)
        self.assertIn("Timer:NE555D", a)
        rows = [l for l in a.splitlines() if l.startswith("| ") and l[2].isdigit()]
        self.assertEqual([r.split("|")[1].strip() for r in rows], ["1", "3", "4", "8"])
        self.assertIn("RST (반전 표기)", a)
        self.assertIn("전원 입력", a)
        self.assertIn("정격", a)

    def test_same_family_variants_with_same_layout_are_mentioned(self):
        a = kp.parts_answer("ne555 pin", self.parts)
        self.assertIn("NE555P", a)
        self.assertIn("핀 배치는 모두 같습니다", a)

    def test_different_layouts_never_get_a_single_guessed_table(self):
        parts = kp.parse_symbol_library(NE_SAMPLE.replace('(name "OUT"', '(name "Q"', 1), "Timer")
        a = kp.parts_answer("NE555 핀", parts)
        self.assertIn("핀 배치가 서로 다릅니다", a)
        self.assertNotIn("| 핀 번호 |", a)
        self.assertIn("Timer:NE555D", a)
        self.assertIn("Timer:NE555P", a)

    def test_digits_only_part_number_is_found_inside_names(self):
        a = kp.parts_answer("555 타이머 핀 설명", self.parts)
        self.assertIn("Timer:NE555D", a)

    def test_question_without_pin_word_or_unknown_part_goes_to_model(self):
        self.assertIsNone(kp.parts_answer("NE555로 LED 깜빡이는 방법", self.parts))
        self.assertIsNone(kp.parts_answer("ZZ999 핀 정보", self.parts))
        self.assertIsNone(kp.parts_answer("IC 핀 정보", self.parts))
        self.assertIsNone(kp.parts_answer("NE555 핀", []))


import importlib.util


@unittest.skipUnless(importlib.util.find_spec("fastapi") and importlib.util.find_spec("httpx"), "fastapi/httpx 미설치")
class ChatPartsLookupTest(unittest.TestCase):
    def setUp(self):
        from unittest import mock
        from fastapi.testclient import TestClient
        import app
        self.app, self.mock = app, mock
        self.client = TestClient(app.app, base_url="http://127.0.0.1:8000", client=("127.0.0.1", 50000))
        self.parts = kp.parse_symbol_library(NE_SAMPLE, "Timer")

    def _ask(self, text, enabled=True):
        with self.mock.patch.object(self.app.kicad_parts, "default_catalog", return_value=self.parts), \
             self.mock.patch.object(self.app.settings, "CHAT_PARTS_LOOKUP", enabled), \
             self.mock.patch.object(self.app, "resolve", side_effect=AssertionError("모델 선택까지 가면 안 됨")):
            return self.client.post("/api/chat", json={"mode": "chat", "provider": "local",
                                                       "messages": [{"role": "user", "content": text}]})

    def test_pin_question_is_answered_without_the_model(self):
        r = self._ask("NE555 IC 핀별 정보")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["model"], "kicad-library")
        self.assertIn("핀 번호", r.json()["answer"])

    def test_switch_off_sends_the_question_to_the_model_path(self):
        with self.assertRaises(AssertionError):
            self._ask("NE555 IC 핀별 정보", enabled=False)


class TerminalWordTest(unittest.TestCase):
    def test_terminal_word_triggers_lookup(self):
        parts = [{"lib_id": "Timer:NE555D", "library": "Timer", "name": "NE555D", "description": "",
                  "footprint": "", "datasheet": "", "pin_count": 2,
                  "pins": [{"number": "1", "name": "GND", "type": "power_in"},
                           {"number": "8", "name": "VCC", "type": "power_in"}]}]
        import kicad_parts
        self.assertIsNotNone(kicad_parts.parts_answer("NE555 각 단자 정보", parts))
        self.assertIsNone(kicad_parts.parts_answer("각 단자 정보", parts))


class RagModeLookupTest(unittest.TestCase):
    def test_document_only_mode_is_not_intercepted_by_the_library(self):
        """2026-11-14 설계 변경: 문서만(rag) 모드는 질문에 부품 이름이 있어도 올려 둔 문서로만 답한다(자동 모드가 판단)."""
        from unittest import mock
        from fastapi.testclient import TestClient
        import app, kicad_parts
        cat = [{"lib_id": "Timer:NE555D", "library": "Timer", "name": "NE555D", "description": "",
                "footprint": "", "datasheet": "", "pin_count": 1,
                "pins": [{"number": "1", "name": "GND", "type": "power_in"}]}]
        with mock.patch.object(kicad_parts, "default_catalog", return_value=cat), \
             mock.patch.object(app, "available_models", return_value=[app.CHAT_MODEL]), \
             mock.patch.object(app, "search_for_chat", return_value=[]) as searched:
            r = TestClient(app.app, base_url="http://127.0.0.1:8000", client=("127.0.0.1", 50000)).post(
                "/api/chat", json={"mode": "rag", "provider": "local",
                                   "messages": [{"role": "user", "content": "NE555 단자 정보"}]})
        self.assertEqual(searched.call_count, 1)
        self.assertNotEqual(r.json().get("model"), "kicad-library")
        self.assertEqual((r.json()["mode"], r.json()["route"]), ("rag", "documents"))


KICAD6_STYLE = '''(kicad_symbol_lib
  (version 20211014)
  (generator https://example.invalid/some-other-tool)
  (symbol "PART_X"
    (in_bom yes)
    (property
      "Reference"
      "U"
      (id 0)
      (at 0 5 0)
    )
    (property "Footprint" "lib:FP_X" (id 2))
    (property "Datasheet" "https://example.invalid/x.pdf" (id 3))
    (symbol "PART_X_0_1"
      (pin
        input line
        (at -5 0 0)
        (length 2)
        (name "IN" (effects (font (size 1 1))))
        (number "1" (effects (font (size 1 1))))
      )
      (pin passive line (at 5 0 180) (length 2) (name "~{OUT}" (effects)) (number "2" (effects)))
    )
  )
)'''


class FormatIndependentParser(unittest.TestCase):
    def test_multiline_old_style_is_read(self):
        ps = kp.parse_symbol_library(KICAD6_STYLE, "other")
        self.assertEqual(len(ps), 1)
        p = ps[0]
        self.assertEqual(p["lib_id"], "other:PART_X")
        self.assertEqual(p["footprint"], "lib:FP_X")
        self.assertEqual(p["datasheet"], "https://example.invalid/x.pdf")
        self.assertEqual([(x["number"], x["name"], x["type"]) for x in p["pins"]],
                         [("1", "IN", "input"), ("2", "~{OUT}", "passive")])

    def test_pin_type_is_never_the_word_number(self):
        # 기존 정규식은 일부 심볼의 첫 핀 유형을 'number'로 잘못 읽었다
        ps = kp.parse_symbol_library(KICAD6_STYLE, "o")
        self.assertTrue(all(x["type"] in ("input", "passive") for x in ps[0]["pins"]))

    def test_not_a_symbol_library_is_refused(self):
        with self.assertRaises(ValueError):
            kp.parse_symbol_library("(kicad_pcb (version 1))", "x")
        with self.assertRaises(ValueError):
            kp.parse_symbol_library("not an sexpr", "x")

    def test_unbalanced_is_refused(self):
        with self.assertRaises(ValueError):
            kp.parse_symbol_library("(kicad_symbol_lib (symbol \"A\"", "x")
        with self.assertRaises(ValueError):
            kp.parse_symbol_library("(kicad_symbol_lib))", "x")

    def test_escaped_quote_in_text(self):
        t = '(kicad_symbol_lib (symbol "A" (property "Reference" "U") (property "Description" "say \\"hi\\"") ))'
        self.assertEqual(kp.parse_symbol_library(t, "l")[0]["description"], 'say "hi"')


FP_TEXT = '''(footprint "R_X"
  (version 20240108)
  (descr "Resistor, test")
  (tags "resistor 0603")
  (attr smd)
  (pad "1" smd roundrect (at -0.8 0) (size 0.8 0.9))
  (pad "2" smd roundrect (at 0.8 0) (size 0.8 0.9))
  (pad "" np_thru_hole circle (at 0 3) (size 1 1) (drill 1))
  (model "${KICAD10_3DMODEL_DIR}/Resistor_SMD.3dshapes/R_X.step" (offset (xyz 0 0 0)))
)'''


class FootprintParser(unittest.TestCase):
    def test_pads_models_and_text(self):
        f = kp.parse_footprint(FP_TEXT, "Resistor_SMD", "R_X")
        self.assertEqual(f["lib_id"], "Resistor_SMD:R_X")
        self.assertEqual(f["pad_numbers"], ["1", "2"])           # 번호 없는 패드는 번호 목록에서 제외
        self.assertEqual(f["pad_count"], 3)
        self.assertEqual(f["attr"], ["smd"])
        self.assertEqual(f["description"], "Resistor, test")
        self.assertEqual(f["tags"], "resistor 0603")
        self.assertEqual(f["models"], ["${KICAD10_3DMODEL_DIR}/Resistor_SMD.3dshapes/R_X.step"])

    def test_old_module_tag_accepted(self):
        f = kp.parse_footprint('(module "M" (pad "1" smd rect (at 0 0)))', "L", "M")
        self.assertEqual(f["pad_numbers"], ["1"])

    def test_not_a_footprint_refused(self):
        with self.assertRaises(ValueError):
            kp.parse_footprint('(kicad_symbol_lib (symbol "A"))', "L", "A")
