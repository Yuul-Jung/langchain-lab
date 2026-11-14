#!/usr/bin/env python3
"""데이터시트 핀 표 추출 도구 비교 — 읽기 전용. data/tools/pdfeval-venv 의 파이썬으로 실행한다.
모든 도구: 같은 쪽(datasheet_pins.candidate_pages) · 같은 후처리(pins_from_tables) · 같은 채점(compare, 정답 KiCad 핀표).
출력은 점수만(데이터시트 본문 없음). 판정 기준은 optimization-log.md 'PyMuPDF 대체 도구' 절에 실행 전 고정.
사용: data/tools/pdfeval-venv/bin/python scripts/eval-pin-tools.py [--tools pdfplumber,camelot-lattice,...]"""
from __future__ import annotations
import argparse, sys, time, warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
warnings.filterwarnings("ignore")
import pymupdf  # noqa: E402
import datasheet_pins as dp  # noqa: E402
import kicad_parts  # noqa: E402

D = Path.home() / "work_datasheets"
DEV = [("SN74AHCT125_TI_datasheet.pdf", "74xx:74AHCT125"), ("FT2232H.PDF", "Interface_USB:FT2232HL"),
       ("1602_CHAR_LCD_WITH_I2C/PCF8574_PCF8574A.pdf", "Interface_Expansion:PCF8574AP")]
HOLD = [("MAX7219-MAX7221.pdf", "Driver_LED:MAX7219"), ("MPU_6050_가속도센서/MPU-6000.PDF", "Sensor_Motion:MPU-6050"),
        ("SN74HCT245_TI_datasheet.pdf", "74xx:74HC245"), ("PCF85263A-372087.pdf", "Timer_RTC:PCF85263AT")]


def cells(rows):
    return [["" if c is None else str(c) for c in r] for r in rows]


def t_pymupdf(path, pages):
    doc = pymupdf.open(path)
    return [cells(t.extract()) for i in pages for t in doc[i].find_tables().tables]


def t_pdfplumber(path, pages):
    import pdfplumber
    with pdfplumber.open(path) as pdf:
        return [cells(t) for i in pages for t in pdf.pages[i].extract_tables()]


def t_camelot(flavor):
    def run(path, pages):
        import camelot
        out = []
        for i in pages:
            try:
                out += [cells(t.df.values.tolist()) for t in camelot.read_pdf(str(path), pages=str(i + 1), flavor=flavor)]
            except Exception:
                pass
        return out
    return run


def t_tabula(lattice):
    def run(path, pages):
        import tabula
        out = []
        for i in pages:
            try:
                dfs = tabula.read_pdf(str(path), pages=i + 1, lattice=lattice, stream=not lattice, multiple_tables=True,
                                      pandas_options={"header": None}, silent=True)
                out += [cells(df.fillna("").astype(str).values.tolist()) for df in dfs]
            except Exception:
                pass
        return out
    return run


def t_docling(path, pages):
    from docling.document_converter import DocumentConverter
    conv = t_docling.conv = getattr(t_docling, "conv", None) or DocumentConverter()
    res = conv.convert(str(path), page_range=(min(pages) + 1, max(pages) + 1)) if pages else None
    if res is None:
        return []
    out = []
    for tb in res.document.tables:
        try:
            df = tb.export_to_dataframe(doc=res.document)
        except TypeError:
            df = tb.export_to_dataframe()
        rows = [list(map(str, df.columns))] + df.fillna("").astype(str).values.tolist()
        out.append(cells(rows))
    return out


TOOLS = {"pymupdf": t_pymupdf, "pdfplumber": t_pdfplumber, "camelot-lattice": t_camelot("lattice"),
         "camelot-stream": t_camelot("stream"), "tabula-lattice": t_tabula(True), "tabula-stream": t_tabula(False),
         "docling": t_docling}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tools", default=",".join(k for k in TOOLS if k != "docling"))
    args = ap.parse_args()
    truth = {p["lib_id"]: p["pins"] for p in kicad_parts.default_catalog()}
    print(f"{'도구':16s} {'dev 재현율':>9s} {'dev 정밀도':>9s} {'holdout 재현율':>13s} {'holdout 정밀도':>13s} {'시간(s)':>7s}  holdout 쌍별 재현율")
    for name in args.tools.split(","):
        fn, res, t0 = TOOLS[name], {}, time.time()
        for group, pairs in (("dev", DEV), ("hold", HOLD)):
            rs = []
            for pdf, lib in pairs:
                path = D / pdf
                pages = dp.candidate_pages(pymupdf.open(str(path)))
                try:
                    tables = fn(path, pages)
                except Exception as e:
                    print(f"  ! {name} {pdf[:20]} 실패: {type(e).__name__}")
                    tables = []
                rs.append(dp.compare(dp.pins_from_tables(tables), truth[lib]))
            res[group] = rs
        m = lambda rs, k: sum(r[k] for r in rs) / len(rs)
        print(f"{name:16s} {m(res['dev'],'recall'):9.3f} {m(res['dev'],'precision'):9.3f} {m(res['hold'],'recall'):13.3f} "
              f"{m(res['hold'],'precision'):13.3f} {time.time()-t0:7.1f}  {[round(r['recall'],2) for r in res['hold']]}")


if __name__ == "__main__":
    main()
