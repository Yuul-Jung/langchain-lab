"""Gate 파이프라인: G0 의도 → G1 합성 → G2 의미/ERC → G3 전기 → G4 출력 → G5 라운드트립 → G6 KiCad ERC → G7 KiCad 라이브러리 대응(심볼 핀 번호·풋프린트 패드).

규칙
- 앞 Gate가 PASS가 아니면 뒤 Gate는 NOT_RUN.
- 각 Gate는 입력/출력 sha256과 finding을 증거로 남긴다. 문자열 'PASS'만 있는 증거는 없다.
- G2/G3가 FAIL이면 KiCad 파일을 만들지 않는다 (실패한 설계가 '쓸 수 있는 파일'로 새어나가지 않게).
- G6를 못 돌리면 최종 상태는 PASS가 아니라 PASS_WITHOUT_KICAD_ERC, G7를 못 돌리면 PASS_WITHOUT_LIBRARY_CHECK.
"""
from __future__ import annotations

import csv
import io
import json
import os
import re

from . import checks, kicad_cli, kicadlib
from .intent import blocking_questions, validate_intent
from .kicad_reader import compare_with_ir, read_schematic
from .kicad_writer import SYM_LIB_TABLE, write_project, write_schematic, write_symbol_library
from .preview import render_svg
from .synth import SynthesisError, sha256_of, synthesize

NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")
GATES = [("G0", "INTENT"), ("G1", "SYNTHESIS"), ("G2", "SEMANTIC_ERC"), ("G3", "ELECTRICAL"),
         ("G4", "EMIT"), ("G5", "ROUNDTRIP"), ("G6", "KICAD_ERC"), ("G7", "KICAD_LIBRARY")]


class HarnessError(Exception):
    pass


def safe_project_dir(out_root: str, name: str) -> str:
    if not NAME_RE.match(name or ""):
        raise HarnessError(f"프로젝트 이름 {name!r}은 [A-Za-z][A-Za-z0-9_-]{{0,63}} 이어야 함")
    root = os.path.realpath(out_root)
    path = os.path.realpath(os.path.join(root, name))
    if os.path.dirname(path) != root:
        raise HarnessError("출력 경로가 out 디렉터리를 벗어남")
    return path


def _gate(gid, status, inp=None, out=None, findings=None, metrics=None):
    name = dict(GATES)[gid]
    return {"gate": gid, "name": name, "status": status,
            "input_sha256": inp, "output_sha256": out,
            "findings": findings or [], "metrics": metrics or {}}


def _status(findings):
    return "FAIL" if checks.has_error(findings) else "PASS"


def bom_rows(ir):
    groups: dict = {}
    for c in ir["components"].values():
        if c["part"] == "PWR_FLAG":
            continue
        key = (c["part"], c["value"], c["footprint"])
        groups.setdefault(key, []).append(c["ref"])
    rows = []
    for (part, value, fp), refs in groups.items():
        rows.append({"refs": " ".join(sorted(refs, key=lambda r: (re.sub(r"\d", "", r), int(re.sub(r"\D", "", r) or 0)))),
                     "qty": len(refs), "part": part, "value": value, "footprint": fp})
    return rows


def _write(path, text):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def run(intent: dict, out_root: str, name: str, run_kicad: bool = True) -> dict:
    pdir = safe_project_dir(out_root, name)
    os.makedirs(pdir, exist_ok=True)
    gates, ir = [], None
    files = {}

    def finish():
        done = {g["gate"] for g in gates}
        for gid, _ in GATES:
            if gid not in done:
                gates.append(_gate(gid, "NOT_RUN"))
        st = [g["status"] for g in gates]
        if "BLOCKED" in st:
            overall = "BLOCKED"
        elif "FAIL" in st:
            overall = "FAIL"
        elif all(x in ("PASS", "SKIPPED") for x in st) and "SKIPPED" in st:
            sk = {g["gate"] for g in gates if g["status"] == "SKIPPED"}
            overall = "PASS_WITHOUT_KICAD_ERC" if "G6" in sk else "PASS_WITHOUT_LIBRARY_CHECK"
        elif all(s == "PASS" for s in st):
            overall = "PASS"
        else:
            overall = "FAIL"
        report = {"project": name, "overall": overall, "gates": gates,
                  "questions": intent.get("questions", []) if isinstance(intent, dict) else [],
                  "assumptions": intent.get("assumptions", []) if isinstance(intent, dict) else [],
                  "files": files}
        _write(os.path.join(pdir, "gate_report.json"), json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        _write(os.path.join(pdir, "report.md"), render_report(report, ir))
        return report

    # G0 ------------------------------------------------------------
    _write(os.path.join(pdir, "intent.json"), json.dumps(intent, ensure_ascii=False, indent=2) + "\n")
    files["intent"] = "intent.json"
    errs = validate_intent(intent)
    ih = sha256_of(intent)
    if errs:
        gates.append(_gate("G0", "FAIL", ih, findings=[checks.F("INTENT_SCHEMA", "ERROR", e) for e in errs]))
        return finish()
    bq = blocking_questions(intent)
    if bq:
        gates.append(_gate("G0", "BLOCKED", ih, findings=[
            checks.F("INTENT_QUESTION", "ERROR", f"{q['id']}: {q['text']}") for q in bq],
            metrics={"blocking_questions": len(bq)}))
        return finish()
    gates.append(_gate("G0", "PASS", ih, metrics={"blocks": len(intent["blocks"]),
                                                  "assumptions": len(intent["assumptions"])}))

    # G1 ------------------------------------------------------------
    try:
        ir = synthesize(intent, name)
    except SynthesisError as e:
        gates.append(_gate("G1", "FAIL", ih, findings=[checks.F("SYNTHESIS", "ERROR", str(e))]))
        return finish()
    irh = sha256_of(ir)
    _write(os.path.join(pdir, "design_ir.json"), json.dumps(ir, ensure_ascii=False, indent=2) + "\n")
    files["design_ir"] = "design_ir.json"
    f1 = checks.structural(ir)
    gates.append(_gate("G1", _status(f1), ih, irh, f1,
                       {"components": len(ir["components"]), "nets": len(ir["nets"])}))
    if gates[-1]["status"] != "PASS":
        return finish()

    # G2, G3 --------------------------------------------------------
    for gid, fn in (("G2", checks.semantic), ("G3", checks.electrical)):
        fs = fn(ir)
        gates.append(_gate(gid, _status(fs), irh, None, fs,
                           {"errors": sum(f["severity"] == "ERROR" for f in fs),
                            "warnings": sum(f["severity"] == "WARN" for f in fs)}))
        if gates[-1]["status"] != "PASS":
            return finish()

    # G4 ------------------------------------------------------------
    sch_text = write_schematic(ir)
    sch_name = f"{name}.kicad_sch"
    _write(os.path.join(pdir, sch_name), sch_text)
    _write(os.path.join(pdir, f"{name}.kicad_pro"), write_project(ir))
    _write(os.path.join(pdir, "eda.kicad_sym"), write_symbol_library(ir))
    _write(os.path.join(pdir, "sym-lib-table"), SYM_LIB_TABLE)
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=["refs", "qty", "part", "value", "footprint"], lineterminator="\n")
    w.writeheader()
    w.writerows(bom_rows(ir))
    _write(os.path.join(pdir, "bom.csv"), buf.getvalue())
    _write(os.path.join(pdir, "preview.svg"), render_svg(sch_text))
    files.update({"schematic": sch_name, "project": f"{name}.kicad_pro", "symbols": "eda.kicad_sym",
                  "sym_lib_table": "sym-lib-table", "bom": "bom.csv", "preview": "preview.svg"})
    sch_hash = sha256_of(sch_text)
    gates.append(_gate("G4", "PASS", irh, sch_hash, metrics={"bytes": len(sch_text.encode())}))

    # G5 ------------------------------------------------------------
    with open(os.path.join(pdir, sch_name), encoding="utf-8") as f:
        disk = f.read()
    f5 = compare_with_ir(ir, read_schematic(disk))
    gates.append(_gate("G5", _status(f5), sha256_of(disk), irh, f5))
    if gates[-1]["status"] != "PASS":
        return finish()

    # G6 ------------------------------------------------------------
    if run_kicad:
        r = kicad_cli.run_erc(os.path.join(pdir, sch_name))
    else:
        r = {"status": "SKIPPED", "findings": [checks.F("KICAD_ERC_DISABLED", "WARN", "--no-kicad 옵션")],
             "metrics": {}}
    gates.append(_gate("G6", r["status"], sch_hash, None, r["findings"], r["metrics"]))
    if gates[-1]["status"] == "FAIL":
        return finish()

    # G7 ------------------------------------------------------------
    st7, f7, m7 = kicadlib.check(ir)
    gates.append(_gate("G7", st7, irh, None, f7, m7))
    return finish()


def render_report(report, ir) -> str:
    L = [f"# {report['project']} — 하네스 리포트", "", f"**최종 상태: {report['overall']}**", "",
         "| Gate | 이름 | 상태 | ERROR | WARN |", "|---|---|---|---|---|"]
    for g in report["gates"]:
        e = sum(f["severity"] == "ERROR" for f in g["findings"])
        w = sum(f["severity"] == "WARN" for f in g["findings"])
        L.append(f"| {g['gate']} | {g['name']} | {g['status']} | {e} | {w} |")
    probs = [(g["gate"], f) for g in report["gates"] for f in g["findings"] if f["severity"] in ("ERROR", "WARN")]
    if probs:
        L += ["", "## 문제 / 경고", ""]
        L += [f"- [{gid}] **{f['severity']}** `{f['code']}` {f['message']}" for gid, f in probs]
    if report["questions"]:
        L += ["", "## 답이 필요한 질문 (intent.json을 수정 후 `--intent`로 재실행)", ""]
        L += [f"- {q['id']} {'(BLOCKING)' if q['blocking'] else ''}: {q['text']}" for q in report["questions"]]
    if report["assumptions"]:
        L += ["", "## 하네스가 둔 가정", ""]
        L += [f"- `{a['field']}` = {a['value']} — {a['reason']}" for a in report["assumptions"]]
    if ir:
        L += ["", "## 블록 설계 근거", ""]
        for bid, b in ir["blocks"].items():
            L.append(f"- **{bid} {b['type']}**: " + ", ".join(f"{k}={v}" for k, v in b["design"].items()))
        L += ["", "## BOM", "", "| Refs | Qty | Part | Value | Footprint |", "|---|---|---|---|---|"]
        L += [f"| {r['refs']} | {r['qty']} | {r['part']} | {r['value']} | {r['footprint']} |" for r in bom_rows(ir)]
    return "\n".join(L) + "\n"
