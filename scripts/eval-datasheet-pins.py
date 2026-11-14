#!/usr/bin/env python3
"""데이터시트 핀 표 추출(datasheet_pins.py) 정확도를 KiCad 핀표와 대조해 잰다 — 읽기 전용.

쌍(데이터시트 → KiCad 부품)은 개발용(dev)과 보류용(holdout)으로 나눈다. 개발 중에는 dev 만 보고,
holdout 은 --holdout 으로 정해 둔 시점에만 본다(볼 때마다 data/eval/graph-results/holdout-looks.log 에 기록).
출력에는 데이터시트 본문을 넣지 않는다 (핀 번호·이름과 점수만).
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import datasheet_pins as dp  # noqa: E402
import kicad_parts  # noqa: E402

D = Path.home() / "work_datasheets"
# 제외: ds3231_rtc_clock.pdf ↔ Timer_RTC:DS3231M — 데이터시트(DS3231, 5~12번 N.C.)와 KiCad 부품(DS3231M, 5~12번 GND)이
#       서로 다른 변형이라 정답이 맞지 않는다 (개발용 첫 실행에서 발견, 보류용을 열기 전에 결정).
DEV = [("SN74AHCT125_TI_datasheet.pdf", "74xx:74AHCT125"),
       ("FT2232H.PDF", "Interface_USB:FT2232HL"),
       ("1602_CHAR_LCD_WITH_I2C/PCF8574_PCF8574A.pdf", "Interface_Expansion:PCF8574AP")]
HOLDOUT = [("MAX7219-MAX7221.pdf", "Driver_LED:MAX7219"),
           ("MPU_6050_가속도센서/MPU-6000.PDF", "Sensor_Motion:MPU-6050"),
           ("SN74HCT245_TI_datasheet.pdf", "74xx:74HC245")]


def run(pairs, verbose):
    parts = {p["lib_id"]: p for p in kicad_parts.default_catalog()}
    rows = []
    for pdf, lib_id in pairs:
        ex = dp.extract_pins(str(D / pdf))
        res = dp.compare(ex, parts[lib_id]["pins"])
        rows.append(res)
        print(f"{pdf[:34]:34s} → {lib_id:28s} 정답 {res['truth']:3d} 추출 {res['extracted']:3d} "
              f"재현율 {res['recall']} 정밀도 {res['precision']} 번호 {res['number_coverage']} 없는 번호 {res['spurious']}")
        if verbose:
            gt = {int(p['number']): p['name'] for p in parts[lib_id]['pins'] if str(p['number']).isdigit()}
            for n in sorted(set(ex) | set(gt)):
                flag = "ok" if n in ex and n in gt and dp.normalize(ex[n]) == dp.normalize(gt[n]) else "XX"
                print(f"    {n:3d} 추출={ex.get(n, '-'):14s} 정답={gt.get(n, '-'):14s} {flag}")
    n = len(rows)
    print(f"  평균 재현율 {sum(r['recall'] for r in rows) / n:.3f}  평균 정밀도 {sum(r['precision'] for r in rows) / n:.3f}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--holdout", action="store_true")
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--label", default="")
    args = ap.parse_args()
    print("== dev ==")
    run(DEV, args.verbose)
    if args.holdout:
        log = ROOT / "data" / "eval" / "graph-results" / "holdout-looks.log"
        with open(log, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now():%Y-%m-%d %H:%M} datasheet-pins label={args.label}\n")
        print("== holdout ==")
        run(HOLDOUT, args.verbose)


if __name__ == "__main__":
    main()
