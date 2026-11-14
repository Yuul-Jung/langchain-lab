"""CLI.

  python -m edaharness run --text "USB-C 5V에서 3.3V LDO, 전원 LED" --name demo --out out
  python -m edaharness run --intent out/demo/intent.json --name demo --out out
  python -m edaharness check out/demo/demo.kicad_sch --ir out/demo/design_ir.json
  python -m edaharness parse "12V 입력, 12V 모터 2A"
"""
from __future__ import annotations

import argparse
import json
import sys

from . import gates
from .intent import parse_text
from .kicad_reader import compare_with_ir, read_schematic

EXIT = {"PASS": 0, "PASS_WITHOUT_KICAD_ERC": 0, "BLOCKED": 2, "FAIL": 1}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="edaharness")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="의도 -> 스키매틱 전체 파이프라인")
    src = r.add_mutually_exclusive_group(required=True)
    src.add_argument("--text")
    src.add_argument("--intent", help="IntentSpec JSON 파일 (질문에 답한 뒤 재실행용)")
    r.add_argument("--name", required=True)
    r.add_argument("--out", default="out")
    r.add_argument("--no-kicad", action="store_true", help="kicad-cli ERC 생략 (G6 SKIPPED)")
    p = sub.add_parser("parse", help="자연어 -> IntentSpec 출력만")
    p.add_argument("text")
    c = sub.add_parser("check", help="기존 스키매틱을 IR과 라운드트립 비교")
    c.add_argument("schematic")
    c.add_argument("--ir", required=True)
    a = ap.parse_args(argv)

    if a.cmd == "parse":
        print(json.dumps(parse_text(a.text), ensure_ascii=False, indent=2))
        return 0
    if a.cmd == "check":
        with open(a.ir, encoding="utf-8") as f:
            ir = json.load(f)
        with open(a.schematic, encoding="utf-8") as f:
            fs = compare_with_ir(ir, read_schematic(f.read()))
        for x in fs:
            print(f"{x['severity']:5} {x['code']}: {x['message']}")
        print("ROUNDTRIP", "FAIL" if any(x["severity"] == "ERROR" for x in fs) else "PASS")
        return 1 if any(x["severity"] == "ERROR" for x in fs) else 0
    if a.text is not None:
        intent = parse_text(a.text)
    else:
        with open(a.intent, encoding="utf-8") as f:
            intent = json.load(f)
    try:
        rep = gates.run(intent, a.out, a.name, run_kicad=not a.no_kicad)
    except gates.HarnessError as e:
        print(f"오류: {e}", file=sys.stderr)
        return 1
    for g in rep["gates"]:
        print(f"{g['gate']} {g['name']:13} {g['status']}")
        for f in g["findings"]:
            if f["severity"] == "ERROR":
                print(f"     ERROR {f['code']}: {f['message']}")
    print(f"최종: {rep['overall']}  ->  {a.out}/{a.name}/report.md")
    return EXIT[rep["overall"]]


if __name__ == "__main__":
    sys.exit(main())
