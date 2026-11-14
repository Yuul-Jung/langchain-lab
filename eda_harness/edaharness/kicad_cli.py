"""선택적 KiCad CLI 연동 (G6). kicad-cli가 없으면 SKIPPED — 절대 PASS가 아니다."""
from __future__ import annotations

import json
import os
import shutil
import subprocess

# 하네스가 의도적으로 생성하는 구조에서 나오는 경고 중, 사유가 문서화된 것만 허용한다.
ALLOWED_WARNINGS = {
    "lib_symbol_mismatch": "임베드 심볼과 프로젝트 라이브러리는 같은 소스에서 생성됨",
}


def find_kicad_cli():
    return os.environ.get("KICAD_CLI") or shutil.which("kicad-cli")


def run_erc(sch_path: str, timeout: int = 120) -> dict:
    exe = find_kicad_cli()
    if not exe:
        return {"status": "SKIPPED", "findings": [{
            "code": "KICAD_CLI_UNAVAILABLE", "severity": "WARN",
            "message": "kicad-cli를 찾지 못해 KiCad 자체 ERC를 실행하지 않음 (KICAD_CLI 환경변수로 지정 가능)",
            "where": ""}], "metrics": {}}
    report = sch_path + ".erc.json"
    cmd = [exe, "sch", "erc", "--format", "json", "--severity-all", "--output", report, sch_path]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"status": "FAIL", "findings": [{"code": "KICAD_ERC_TIMEOUT", "severity": "ERROR",
                                                "message": "kicad-cli ERC 시간 초과", "where": ""}], "metrics": {}}
    if not os.path.exists(report):
        return {"status": "FAIL", "findings": [{"code": "KICAD_ERC_NO_REPORT", "severity": "ERROR",
                                                "message": f"ERC 리포트 없음: {proc.stderr[-500:]}", "where": ""}],
                "metrics": {"returncode": proc.returncode}}
    with open(report, encoding="utf-8") as f:
        data = json.load(f)
    return evaluate_erc_report(data)


def evaluate_erc_report(data: dict) -> dict:
    """kicad-cli ERC JSON 평가. 형식을 모르면 fail-closed."""
    sheets = data.get("sheets")
    if not isinstance(sheets, list):
        return {"status": "FAIL", "findings": [{"code": "KICAD_ERC_FORMAT", "severity": "ERROR",
                                                "message": "ERC JSON에 sheets 배열이 없음 — 형식 미확인", "where": ""}],
                "metrics": {}}
    findings, n_err, n_warn = [], 0, 0
    for sh in sheets:
        for v in sh.get("violations", []):
            sev = str(v.get("severity", "error")).lower()
            typ = v.get("type", "?")
            if sev == "error":
                n_err += 1
                findings.append({"code": f"KICAD_ERC:{typ}", "severity": "ERROR",
                                 "message": v.get("description", ""), "where": sh.get("path", "")})
            elif sev == "warning":
                n_warn += 1
                allowed = typ in ALLOWED_WARNINGS
                findings.append({"code": f"KICAD_ERC:{typ}", "severity": "WARN" if allowed else "ERROR",
                                 "message": v.get("description", "") +
                                 (f" (허용: {ALLOWED_WARNINGS[typ]})" if allowed else " (허용 목록에 없는 경고)"),
                                 "where": sh.get("path", "")})
    status = "FAIL" if any(f["severity"] == "ERROR" for f in findings) else "PASS"
    return {"status": status, "findings": findings,
            "metrics": {"errors": n_err, "warnings": n_warn}}
