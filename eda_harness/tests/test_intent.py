import unittest

from helpers import clone, intent
from edaharness import adapters
from edaharness.intent import blocking_questions, parse_text, validate_intent


class Parser(unittest.TestCase):
    def test_usb_ldo_led(self):
        it = intent("usb_ldo")
        self.assertEqual(it["power_input"], {"connector": "usb_c", "voltage_v": 5.0})
        self.assertEqual([b["type"] for b in it["blocks"]], ["ldo", "led_indicator"])
        self.assertEqual(it["blocks"][0]["params"]["iout_max_a"], 0.3)
        self.assertEqual(it["blocks"][1]["params"]["rail"], "B1")
        self.assertEqual(it["blocks"][1]["params"]["color"], "green")
        self.assertEqual(validate_intent(it), [])

    def test_motor(self):
        b = intent("motor")["blocks"][0]
        self.assertEqual(b["type"], "lowside_switch")
        self.assertEqual(b["params"]["load_current_a"], 2.0)
        self.assertTrue(b["params"]["inductive"])
        self.assertEqual(b["params"]["control_v"], 3.3)

    def test_3v3_notation_and_arrow(self):
        it = parse_text("12V 입력에서 3V3 LDO")
        self.assertEqual(it["blocks"][0]["params"]["vout_v"], 3.3)
        it = parse_text("5V에서 1.8V로 변환")
        self.assertEqual(it["blocks"][0]["params"]["vout_v"], 1.8)

    def test_milliamp(self):
        it = parse_text("5V 입력에서 3.3V LDO 출력 150mA")
        self.assertAlmostEqual(it["blocks"][0]["params"]["iout_max_a"], 0.15)

    def test_defaults_are_recorded(self):
        it = parse_text("9V 입력 LED 깜빡이")
        fields = {a["field"] for a in it["assumptions"]}
        self.assertIn("blocks.blinker_555.freq_hz", fields)
        self.assertIn("led.color", fields)

    def test_missing_vout_blocks(self):
        self.assertTrue(blocking_questions(parse_text("5V 입력 LDO")))

    def test_unsupported_vout_blocks(self):
        q = blocking_questions(parse_text("5V 입력에서 3.0V LDO"))
        self.assertTrue(any("라이브러리에 없" in x["text"] for x in q))

    def test_missing_input_blocks(self):
        self.assertTrue(blocking_questions(parse_text("전원 LED 하나")))

    def test_missing_load_current_blocks(self):
        self.assertTrue(blocking_questions(parse_text("12V 입력 모터 제어")))

    def test_load_voltage_mismatch_blocks(self):
        q = blocking_questions(parse_text("5V 입력, 12V 모터 1A"))
        self.assertTrue(any("부하 전압" in x["text"] for x in q))

    def test_unclassified_number_is_not_dropped(self):
        it = parse_text("5V 입력에서 3.3V LDO, 그리고 47V")
        self.assertIn("47V", it["unparsed"])
        self.assertTrue(blocking_questions(it))

    def test_nothing_recognized(self):
        self.assertTrue(blocking_questions(parse_text("저항 하나")))


class Validation(unittest.TestCase):
    def setUp(self):
        self.ok = intent("usb_ldo")

    def test_closed_top_level(self):
        x = clone(self.ok)
        x["components"] = {}
        self.assertTrue(any("허용되지 않은 키" in e for e in validate_intent(x)))

    def test_closed_params(self):
        x = clone(self.ok)
        x["blocks"][0]["params"]["r_ohm"] = 100
        self.assertTrue(validate_intent(x))

    def test_unknown_block_type(self):
        x = clone(self.ok)
        x["blocks"][0]["type"] = "buck"
        self.assertTrue(any("지원하지 않는 블록" in e for e in validate_intent(x)))

    def test_rail_must_reference_earlier_ldo(self):
        x = clone(self.ok)
        x["blocks"][1]["params"]["rail"] = "B9"
        self.assertTrue(validate_intent(x))
        x["blocks"].reverse()   # LED가 LDO보다 앞서면 안 됨
        x["blocks"][0]["params"]["rail"] = "B1"
        self.assertTrue(validate_intent(x))

    def test_usb_only_5v(self):
        x = clone(self.ok)
        x["power_input"]["voltage_v"] = 9.0
        self.assertTrue(validate_intent(x))

    def test_bool_is_not_number(self):
        x = clone(self.ok)
        x["blocks"][0]["params"]["iout_max_a"] = True
        self.assertTrue(validate_intent(x))

    def test_led_current_limit(self):
        x = clone(self.ok)
        x["blocks"][1]["params"]["current_a"] = 0.05
        self.assertTrue(validate_intent(x))


class Adapters(unittest.TestCase):
    def good(self):
        x = intent("usb_ldo")
        x["source"] = {"kind": "text", "text": "위조"}
        return adapters.json.dumps(x)

    def test_llm_accepts_valid_and_overwrites_source(self):
        out = adapters.intent_from_llm(lambda p: "```json\n" + self.good() + "\n```", "원문")
        self.assertEqual(out["source"], {"kind": "llm", "text": "원문"})

    def test_llm_prompt_mentions_contract(self):
        seen = {}
        adapters.intent_from_llm(lambda p: seen.setdefault("p", p) and self.good(), "x")
        self.assertIn("KiCad 내용은 절대 만들지", seen["p"])

    def test_llm_rejects_prose(self):
        with self.assertRaises(adapters.AdapterError):
            adapters.intent_from_llm(lambda p: "물론입니다! " + self.good(), "x")

    def test_llm_rejects_schema_violation(self):
        bad = adapters.json.loads(self.good())
        bad["blocks"][0]["params"]["netlist"] = "U1.2-+3V3"
        with self.assertRaises(adapters.AdapterError):
            adapters.intent_from_llm(lambda p: adapters.json.dumps(bad), "x")

    def test_image_magic_and_size(self):
        self.assertEqual(adapters.check_image(b"\x89PNG\r\n\x1a\n...."), "png")
        with self.assertRaises(adapters.AdapterError):
            adapters.check_image(b"GIF89a")
        with self.assertRaises(adapters.AdapterError):
            adapters.check_image(b"\xff\xd8\xff" + b"0" * adapters.MAX_IMAGE_BYTES)

    def test_vision_low_confidence_becomes_question(self):
        it = intent("usb_ldo")
        out = adapters.intent_from_image(
            lambda b: {"intent": clone(it), "confidence": {"blocks/B1": 0.95, "blocks/B2": 0.4}},
            b"\x89PNG\r\n\x1a\nxx")
        self.assertEqual([b["id"] for b in out["blocks"]], ["B1"])
        self.assertTrue(blocking_questions(out))
        self.assertEqual(out["source"]["kind"], "image")

    def test_vision_missing_confidence_rejected(self):
        it = intent("usb_ldo")
        with self.assertRaises(adapters.AdapterError):
            adapters.intent_from_image(lambda b: {"intent": it, "confidence": {}}, b"\x89PNG\r\n\x1a\n")


if __name__ == "__main__":
    unittest.main()
