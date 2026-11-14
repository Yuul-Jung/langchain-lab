import json
import os
import shutil
import tempfile
import unittest

from helpers import intent
from edaharness import gates, kicad_cli
from edaharness.cli import main
from edaharness.intent import parse_text
from edaharness.synth import sha256_of


class Pipeline(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def run_(self, it, name="p", **kw):
        return gates.run(it, self.tmp, name, run_kicad=False, **kw)

    def statuses(self, rep):
        return [g["status"] for g in rep["gates"]]

    def test_pass_without_kicad(self):
        rep = self.run_(intent("mix"))
        self.assertEqual(rep["overall"], "PASS_WITHOUT_KICAD_ERC")
        self.assertEqual(self.statuses(rep), ["PASS"] * 6 + ["SKIPPED", "PASS"])
        for f in ("p.kicad_sch", "p.kicad_pro", "eda.kicad_sym", "sym-lib-table", "bom.csv",
                  "design_ir.json", "gate_report.json", "report.md", "intent.json"):
            self.assertTrue(os.path.exists(os.path.join(self.tmp, "p", f)), f)

    def test_evidence_hashes_match_disk(self):
        rep = self.run_(intent("usb_ldo"))
        d = os.path.join(self.tmp, "p")
        with open(os.path.join(d, "design_ir.json"), encoding="utf-8") as f:
            irh = sha256_of(json.load(f))
        with open(os.path.join(d, "p.kicad_sch"), encoding="utf-8") as f:
            schh = sha256_of(f.read())
        g = {x["gate"]: x for x in rep["gates"]}
        self.assertEqual(g["G1"]["output_sha256"], irh)
        self.assertEqual(g["G2"]["input_sha256"], irh)
        self.assertEqual(g["G4"]["output_sha256"], schh)
        self.assertEqual(g["G5"]["input_sha256"], schh)
        self.assertEqual(g["G0"]["input_sha256"], sha256_of(intent("usb_ldo")))

    def test_blocked_stops_everything(self):
        rep = self.run_(parse_text("LDO 하나"))
        self.assertEqual(rep["overall"], "BLOCKED")
        self.assertEqual(self.statuses(rep)[1:], ["NOT_RUN"] * 7)
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "p", "design_ir.json")))

    def test_electrical_fail_emits_no_kicad_files(self):
        rep = self.run_(parse_text("12V 입력에서 3V3 LDO, 파란 전원 LED"))
        self.assertEqual(rep["overall"], "FAIL")
        self.assertEqual(rep["gates"][3]["status"], "FAIL")
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "p", "p.kicad_sch")))
        self.assertTrue(os.path.exists(os.path.join(self.tmp, "p", "design_ir.json")))

    def test_synthesis_fail(self):
        rep = self.run_(parse_text("USB 입력에서 5V LDO"))
        self.assertEqual(rep["gates"][1]["status"], "FAIL")

    def test_invalid_intent_fail(self):
        it = intent("usb_ldo")
        it["blocks"][0]["type"] = "buck"
        rep = self.run_(it)
        self.assertEqual(rep["gates"][0]["status"], "FAIL")

    def test_answer_loop(self):
        """BLOCKED -> 사용자가 intent.json에 답 -> 재실행 PASS."""
        rep = self.run_(parse_text("5V 입력 LDO"))
        self.assertEqual(rep["overall"], "BLOCKED")
        with open(os.path.join(self.tmp, "p", "intent.json"), encoding="utf-8") as f:
            it = json.load(f)
        it["blocks"] = [{"id": "B1", "type": "ldo",
                         "params": {"rail_in": "INPUT", "vout_v": 3.3, "iout_max_a": 0.2}}]
        it["questions"] = []
        self.assertEqual(self.run_(it)["overall"], "PASS_WITHOUT_KICAD_ERC")

    def test_bad_names_rejected(self):
        for bad in ("../x", "a/b", "", ".hidden", "x" * 80, "1abc", "a b"):
            with self.assertRaises(gates.HarnessError, msg=bad):
                self.run_(intent("usb_ldo"), name=bad)

    def test_report_mentions_failures(self):
        self.run_(parse_text("12V 입력에서 3V3 LDO, 파란 전원 LED"))
        with open(os.path.join(self.tmp, "p", "report.md"), encoding="utf-8") as f:
            md = f.read()
        self.assertIn("LDO_THERMAL", md)
        self.assertIn("**최종 상태: FAIL**", md)

    def test_cli_exit_codes(self):
        self.assertEqual(main(["run", "--text", "USB 입력에서 3.3V LDO", "--name", "a",
                               "--out", self.tmp, "--no-kicad"]), 0)
        self.assertEqual(main(["run", "--text", "LDO 하나", "--name", "b",
                               "--out", self.tmp, "--no-kicad"]), 2)
        self.assertEqual(main(["run", "--text", "12V 입력에서 3V3 LDO", "--name", "c",
                               "--out", self.tmp, "--no-kicad"]), 1)
        d = os.path.join(self.tmp, "a")
        self.assertEqual(main(["check", os.path.join(d, "a.kicad_sch"),
                               "--ir", os.path.join(d, "design_ir.json")]), 0)


class KiCadErcPolicy(unittest.TestCase):
    def test_unknown_format_fails_closed(self):
        self.assertEqual(kicad_cli.evaluate_erc_report({"foo": 1})["status"], "FAIL")

    def test_error_fails(self):
        r = kicad_cli.evaluate_erc_report({"sheets": [{"path": "/", "violations": [
            {"severity": "error", "type": "pin_not_driven", "description": "x"}]}]})
        self.assertEqual(r["status"], "FAIL")

    def test_allowed_warning_passes(self):
        r = kicad_cli.evaluate_erc_report({"sheets": [{"path": "/", "violations": [
            {"severity": "warning", "type": "lib_symbol_mismatch", "description": "x"}]}]})
        self.assertEqual(r["status"], "PASS")

    def test_unlisted_warning_fails(self):
        r = kicad_cli.evaluate_erc_report({"sheets": [{"path": "/", "violations": [
            {"severity": "warning", "type": "label_dangling", "description": "x"}]}]})
        self.assertEqual(r["status"], "FAIL")

    def test_clean_passes(self):
        self.assertEqual(kicad_cli.evaluate_erc_report({"sheets": [{"path": "/", "violations": []}]})["status"],
                         "PASS")

    def test_missing_cli_is_skipped_not_pass(self):
        old = os.environ.pop("KICAD_CLI", None)
        old_path = os.environ.get("PATH", "")
        os.environ["PATH"] = ""
        try:
            self.assertEqual(kicad_cli.run_erc("/nonexistent.kicad_sch")["status"], "SKIPPED")
        finally:
            os.environ["PATH"] = old_path
            if old is not None:
                os.environ["KICAD_CLI"] = old


if __name__ == "__main__":
    unittest.main()
