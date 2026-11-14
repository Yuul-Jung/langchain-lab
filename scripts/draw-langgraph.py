#!/usr/bin/env python3
"""LangGraph 두 그래프(문서 RAG · 부품 추천)를 그림으로 본다 — 읽기 전용, 서버·모델 필요 없음.
출력: data/graph-views/graphs.html (브라우저로 열기) + 같은 폴더의 *.mmd (Mermaid 원문; VS Code 마크다운 미리보기에서도 보임).
사용: .venv/bin/python scripts/draw-langgraph.py [--open]"""
from __future__ import annotations
import argparse, html, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import parts_graph as pg, rag_graph as rg  # noqa: E402

OUT = ROOT / "data" / "graph-views"


def graphs():
    rag = rg.build_rag_graph(rg.RagDeps(search=lambda q: [], generate=lambda q, c, f: "", verify=True, cite=True))
    parts = pg.build_parts_graph(pg.PartsDeps(find=lambda q, n: ([], "file")))
    return [("문서 RAG 그래프 (rag_graph.py) — 검증·인용을 켠 모양", "rag", rag),
            ("부품 추천 그래프 (parts_graph.py)", "parts", parts)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--open", action="store_true")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    blocks = []
    for title, key, g in graphs():
        mmd = g.get_graph().draw_mermaid()
        (OUT / f"{key}.mmd").write_text(mmd, encoding="utf-8")
        blocks.append(f"<h2>{html.escape(title)}</h2><pre class='mermaid'>{html.escape(mmd)}</pre>")
    page = ("<!doctype html><meta charset='utf-8'><title>LangGraph 구조</title>"
            "<style>body{font-family:sans-serif;max-width:1000px;margin:24px auto;padding:0 16px}h2{margin-top:32px}</style>"
            + "".join(blocks) +
            "<script type='module'>import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@10.9.1/dist/mermaid.esm.min.mjs';"
            "mermaid.initialize({startOnLoad:true});</script>")
    (OUT / "graphs.html").write_text(page, encoding="utf-8")
    print("저장:", OUT / "graphs.html")
    if args.open:
        subprocess.Popen(["xdg-open", str(OUT / "graphs.html")])


if __name__ == "__main__":
    main()
