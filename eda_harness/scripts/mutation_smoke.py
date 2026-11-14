"""뮤테이션 스모크: 핵심 검사 한 줄을 일부러 망가뜨렸을 때 테스트가 실패하는지 확인한다.

테스트가 모두 통과해도 '검사가 실제로 무언가를 잡는지'는 별개다. 이 스크립트는
각 뮤테이션마다 소스 사본을 만들어 테스트를 돌리고, 살아남은 뮤턴트(=테스트 공백)를 보고한다.

    python scripts/mutation_smoke.py
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

MUTANTS = [
    ("edaharness/kicad_reader.py", "if a != b:", "if False:", "G5 넷 비교 생략"),
    ("edaharness/kicad_reader.py", "if _on_segment(pt, a, b):", "if False:", "라벨-와이어 중간 연결 무시"),
    ("edaharness/kicad_writer.py", "return round(sx + pin.x, 4), round(sy - pin.y, 4)",
     "return round(sx + pin.x, 4), round(sy + pin.y, 4)", "핀 y축 뒤집힘"),
    ("edaharness/checks.py", 'if "power_in" in types and n_pout == 0:', "if False:", "power_in 미구동 검사 생략"),
    ("edaharness/checks.py", 'if n["external_supply"] and name not in flagged:', "if False:", "PWR_FLAG 검사 생략"),
    ("edaharness/checks.py", "if n_pout > 1:", "if False:", "전원 단락 검사 생략"),
    ("edaharness/checks.py", "if err > 0.10:", "if False:", "555 주파수 검사 생략"),
    ("edaharness/checks.py", 'if vc < pr["rds_spec_vgs_v"]:', "if False:", "MOSFET 게이트 구동 검사 생략"),
    ("edaharness/checks.py", 'if p["inductive"]:', "if False:", "플라이백 검사 생략"),
    ("edaharness/checks.py", "if pd > pd_max:", "if False:", "LDO 열 검사 생략"),
    ("edaharness/synth.py", 'r = e_nearest(head / i_target, mode="ceil")',
     "r = e_nearest(head / i_target)", "LED 저항 올림 대신 반올림"),
    ("edaharness/intent.py", "    for raw in unparsed:", "    for raw in []:", "분류 못한 숫자 사양 무시"),
    ("edaharness/gates.py", '            return finish()\n\n    # G4', "\n    # G4", "G3 실패해도 KiCad 파일 출력"),
    ("edaharness/kicad_cli.py", 'return {"status": "SKIPPED"', 'return {"status": "PASS"', "kicad-cli 없을 때 PASS"),
    ("edaharness/checks.py", 'if hi > p["sink_vmax_v"]:', "if False:", "레벨 변환 과전압 검사 생략"),
    ("edaharness/checks.py", 'if lo < p["sink_vih_min_v"]:', "if False:", "레벨 변환 High 인식 검사 생략"),
    ("edaharness/checks.py", 'if i_src > p["src_iout_max_a"]:', "if False:", "레벨 변환 구동 전류 검사 생략"),
    ("edaharness/checks.py", "if tr > 0.1 / p[\"signal_max_hz\"]:", "if False:", "레벨 변환 상승 시간 검사 생략"),
    ("edaharness/units.py", "hi = v_hi * r_bot * (1 + r_tol)", "hi = v_hi * r_bot * (1 - r_tol)", "분압 최악 상한 계산 오류"),
    ("edaharness/synth.py", "if hi > vmx or lo < vih:", "if False:", "분압 합성이 창 조건을 무시"),
    ("edaharness/checks.py", 'if v is None or not (e["min_v"] <= v <= e["max_v"]):', "if False:", "모듈 전원 범위 검사 생략"),
    ("edaharness/checks.py", 'if e["host_voh_max_v"] > e["vmax_v"]:\n                out.append(F("MODULE_IN_VMAX"',
     'if False:\n                out.append(F("MODULE_IN_VMAX"', "모듈 입력 과전압 검사 생략"),
    ("edaharness/checks.py", 'if e["host_voh_min_v"] < e["vih_min_v"]:\n                out.append(F("MODULE_IN_VIH"',
     'if False:\n                out.append(F("MODULE_IN_VIH"', "모듈 입력 High 인식 검사 생략"),
    ("edaharness/checks.py", "        if not any(c[\"pins\"].get(\"1\") == net", "        if False and not any(c[\"pins\"].get(\"1\") == net", "모듈 디커플링 검사 생략"),
    ("edaharness/checks.py", 'if e["role"] == "gnd" and j["pins"].get(num) != "GND":', 'if False:', "접지 핀 연결 검사 생략"),
    ("edaharness/checks.py", 'elif e["role"] == "nc" and num not in j["no_connect"]:', "elif False:", "NC 핀 검사 생략"),
    ("edaharness/checks.py", "if len(set(host_nets)) != len(host_nets):", "if False:", "호스트 신호 넷 공유 검사 생략"),
    ("edaharness/checks.py", 'if not p["pin_order_verified"]:', "if False:", "핀 순서 미확인 경고 생략"),
    ("edaharness/synth.py", 'if e["host_voh_max_v"] > e["vmax_v"]:\n                raise', 'if False:\n                raise', "합성이 호스트 과전압 허용"),
    ("edaharness/synth.py", 'if not (e["min_v"] <= v <= e["max_v"]):', "if False:", "합성이 전원 범위 무시"),
    ("edaharness/intent.py", 'if "vcc" not in roles or "gnd" not in roles:', "if False:", "전원/접지 핀 없는 모듈 허용"),
    ("edaharness/boards.py", "if len(pins) != raw_count[h]:", "if False:", "XDC 읽은 줄 수 불일치 무시"),
    ("edaharness/kicadlib.py", "if set(ks) != set(mine):", "if False:", "G7 심볼 핀 번호 대조 생략"),
    ("edaharness/kicadlib.py", "        if miss:", "        if False:", "G7 패드 누락 검사 생략"),
    ("edaharness/kicadlib.py", "        if pads is None:", "        if False:", "G7 풋프린트 파일 존재 검사 생략"),
    ("edaharness/kicadlib.py", "    if not sym_dir or not fp_dir:", "    if False:", "G7 라이브러리 없을 때 SKIPPED 대신 진행"),
    ("edaharness/library.py", 'd_num="3", s_num="2"))', 'd_num="2", s_num="3"))', "AO3400A 드레인/소스 번호 되돌림"),
]


def run_tests(root):
    r = subprocess.run([sys.executable, "-m", "unittest", "-q"], cwd=os.path.join(root, "tests"),
                       capture_output=True, text=True)
    return r.returncode == 0


def main():
    if not run_tests(ROOT):
        print("원본 테스트가 실패함 — 먼저 고칠 것")
        return 2
    survived = []
    for rel, old, new, label in MUTANTS:
        with tempfile.TemporaryDirectory() as tmp:
            dst = os.path.join(tmp, "w")
            shutil.copytree(ROOT, dst, ignore=shutil.ignore_patterns("__pycache__", "out", ".git"))
            path = os.path.join(dst, rel)
            with open(path, encoding="utf-8") as f:
                src = f.read()
            if old not in src:
                print(f"[STALE ] {label}: 대상 코드가 바뀜 — MUTANTS 갱신 필요")
                survived.append(label)
                continue
            with open(path, "w", encoding="utf-8") as f:
                f.write(src.replace(old, new, 1))
            killed = not run_tests(dst)
            print(f"[{'KILLED' if killed else 'ALIVE '}] {label}")
            if not killed:
                survived.append(label)
    print(f"\n뮤턴트 {len(MUTANTS)}개 중 생존 {len(survived)}개")
    return 1 if survived else 0


if __name__ == "__main__":
    sys.exit(main())
