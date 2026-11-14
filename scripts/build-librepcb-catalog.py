#!/usr/bin/env python3
"""내려받은 LibrePCB 라이브러리(data/library_staging/librepcb/*.lplib)를 부품 카탈로그로 만든다 (읽기 전용).

결과(모두 data/library_staging/librepcb/ 아래, GitHub에 올라가지 않음):
  catalog.jsonl     장치마다 한 줄 (이름·설명·분류·제조사·부품 번호·데이터시트·핀 표). 전부 review_status=proposed
  SOURCE.json       저장소별 커밋·라이선스 파일 확인 결과·만든 날짜
  link_report.json  연결 점검: 컴포넌트·패키지를 못 찾은 장치, 핀 이름이 없는 장치, 읽지 못한 파일
KiCad 카탈로그(data/kicad_catalog)는 건드리지 않는다.
사용: .venv/bin/python scripts/build-librepcb-catalog.py
"""
from __future__ import annotations

import json
import subprocess
import sys
from collections import Counter
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import librepcb_parts  # noqa: E402

BASE = ROOT / "data" / "library_staging" / "librepcb"


def main() -> int:
    libs = sorted(p for p in BASE.glob("*.lplib") if p.is_dir())
    if not libs:
        print("라이브러리가 없습니다:", BASE)
        return 2
    lib = librepcb_parts.Library()
    sources = []
    checked = {}
    check_file = BASE / "_licenses_checked.json"
    if check_file.exists():
        checked = {r["repo"]: r for r in json.loads(check_file.read_text(encoding="utf-8"))}
    for path in libs:
        commit = subprocess.run(["git", "-C", str(path), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
        lib.add_library(path, commit=commit)
        c = checked.get(path.name, {})
        sources.append({"repo": path.name, "commit": commit, "license_file": c.get("license_file"),
                        "cc0_text_found": c.get("cc0_text_found")})
    entries, report = lib.build()
    with (BASE / "catalog.jsonl").open("w", encoding="utf-8") as fh:
        for e in entries:
            fh.write(json.dumps(e, ensure_ascii=False) + "\n")
    roles = Counter(p["role"] for e in entries for p in e["pins"])
    report.update({"libraries": len(libs), "entries": len(entries), "pin_roles": dict(roles.most_common()),
                   "read_error_examples": lib.errors[:10], "with_datasheet": sum(1 for e in entries if e["datasheets"]),
                   "with_manufacturer": sum(1 for e in entries if e["manufacturers"]),
                   "with_category": sum(1 for e in entries if e["category"])})
    (BASE / "link_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    (BASE / "SOURCE.json").write_text(json.dumps({
        "source": "LibrePCB-Libraries (GitHub 조직)", "license": "CC0-1.0",
        "license_note": "각 저장소의 LICENSE.txt 에 CC0 1.0 Universal 전문이 있는 것을 직접 확인(cc0_text_found)",
        "built": date.today().isoformat(), "repos": sources}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"저장소 {len(libs)}개 → 장치 {len(entries)}개 (pins {sum(e['pin_count'] for e in entries):,})")
    print("연결 점검:", {k: v for k, v in report.items() if k in ("missing_component", "missing_package", "pads_unresolved", "no_pins", "deprecated", "read_errors")})
    print("있는 항목: 데이터시트", report["with_datasheet"], "· 제조사", report["with_manufacturer"], "· 분류", report["with_category"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
