#!/usr/bin/env python3
"""KiCad 공식 라이브러리(심볼·풋프린트·3D)에서 필요한 정보를 모두 읽어 data/kicad_catalog/ 에 저장한다 (읽기 전용).

만드는 것
  catalog.jsonl      심볼 부품 목록(build-kicad-catalog.py 와 같은 결과)
  footprints.jsonl   풋프린트 목록(패드 번호·유형·모양, 설명, 태그, 3D 모델 경로)
  link_report.json   심볼↔풋프린트↔3D 연결 무결성 통계와 문제 목록
  SOURCE.json        출처(Flatpak 확장 이름·커밋·버전), 라이선스, 가져온 날짜
3D 모델 파일(수 GB)은 복사하지 않고 있는지만 확인한다. 결과는 data/ 아래에만 저장되고 GitHub에 올라가지 않는다.
라이선스: KiCad 공식 라이브러리는 CC-BY-SA 4.0 + 설계 예외. 이 파일들은 파생 모음이므로 재배포하지 않는다.
"""
import datetime
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import kicad_parts  # noqa: E402

OUT = ROOT / "data" / "kicad_catalog"
EXT = {"symbols": "org.kicad.KiCad.Library.Symbols", "footprints": "org.kicad.KiCad.Library.Footprints",
       "3d": "org.kicad.KiCad.Library.Packages3D"}


def info(ref: str) -> dict:
    out = subprocess.run(["flatpak", "info", "--user", ref], capture_output=True, text=True)
    if out.returncode != 0:
        raise SystemExit(f"{ref} 를 찾지 못했습니다 (flatpak --user 로 설치되어 있어야 함).")
    d = {}
    for line in out.stdout.splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            d[k.strip()] = v.strip()
    loc = subprocess.run(["flatpak", "info", "--user", "--show-location", ref], capture_output=True, text=True).stdout.strip()
    d["location"] = loc
    return d


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    meta = {k: info(v) for k, v in EXT.items()}
    sym_dir = Path(meta["symbols"]["location"]) / "files" / "symbols"
    fp_dir = Path(meta["footprints"]["location"]) / "files" / "footprints"
    d3_dir = Path(meta["3d"]["location"]) / "files" / "3dmodels"

    parts = kicad_parts.load_catalog(sym_dir)
    kicad_parts.save_catalog(parts, OUT / "catalog.jsonl")
    fps = kicad_parts.load_footprints(fp_dir)
    failed = getattr(kicad_parts.load_footprints, "failed", [])
    with open(OUT / "footprints.jsonl", "w", encoding="utf-8") as f:
        for p in fps:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")

    fpm = {p["lib_id"]: p for p in fps}
    # 심볼 -> 풋프린트 연결
    linked = broken = covered = uncovered = 0
    broken_list, uncovered_list = [], []
    for p in parts:
        ref = p["footprint"]
        if not ref:
            continue
        linked += 1
        fp = fpm.get(ref)
        if fp is None:
            broken += 1
            if len(broken_list) < 200:
                broken_list.append({"symbol": p["lib_id"], "footprint": ref})
            continue
        need = {x["number"] for x in p["pins"] if x["type"] != "no_connect"}
        miss = sorted(need - set(fp["pad_numbers"]))
        if miss:
            uncovered += 1
            if len(uncovered_list) < 200:
                uncovered_list.append({"symbol": p["lib_id"], "footprint": ref, "pins_without_pad": miss[:8]})
        else:
            covered += 1
    # 풋프린트 -> 3D 모델 존재
    m_total = m_ok = 0
    m_missing = []
    for p in fps:
        for m in p["models"]:
            m_total += 1
            rel = m.split("}", 1)[-1].lstrip("/\\") if "${" in m else m
            if (d3_dir / rel).is_file():
                m_ok += 1
            elif len(m_missing) < 200:
                m_missing.append({"footprint": p["lib_id"], "model": m})
    report = {
        "symbols": len(parts), "footprints": len(fps), "footprint_files_unreadable": failed[:50],
        "symbols_with_footprint_link": linked, "links_to_missing_footprint": broken,
        "links_pads_cover_all_pins": covered, "links_with_pins_lacking_pads": uncovered,
        "models_referenced": m_total, "models_found": m_ok, "models_missing": m_total - m_ok,
        "samples": {"broken_links": broken_list[:20], "pins_without_pad": uncovered_list[:20],
                    "missing_models": m_missing[:20]},
    }
    (OUT / "link_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    source = {"fetched": datetime.date.today().isoformat(),
              "license": "CC-BY-SA 4.0 with exception (KiCad libraries). 파생 모음이므로 재배포하지 않는다.",
              "extensions": {k: {kk: v.get(kk) for kk in ("ID", "Ref", "Arch", "Branch", "Version", "Commit", "Installed")}
                             for k, v in meta.items()}}
    (OUT / "SOURCE.json").write_text(json.dumps(source, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "samples"}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
