#!/usr/bin/env python3
"""한·영 다리 1단계: 말뭉치에서 영어 기술 용어·구절을 캔다 (질문 세트는 보지 않는다 — 과적합 방지).

말뭉치: KiCad 카탈로그 설명·키워드(부품마다 1건) + 데이터시트 색인 청크(langchain_datasheets_v1, 청크마다 1건).
1~3 낱말 구절의 문서 빈도(몇 건에 나왔나)를 세고, 양 끝이 기능어가 아닌 것, 숫자·단위만이 아닌 것만 남긴다.
출력: data/ontology/bridge_candidates.jsonl  {"en", "df_kicad", "df_datasheet", "words"}
사용: .venv/bin/python scripts/mine-bridge-phrases.py [--top 500] [--no-datasheets]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
OUT = ROOT / "data" / "ontology" / "bridge_candidates.jsonl"

STOP = set("""a an the of in on at to for from with by and or is are be as it its this that these those which
not no than then into over under per via vs up down out off only also all any each other such can may will
one two three four five six seven eight nine ten see note notes figure table page section typical typ min max
datasheet rev copyright inc ltd corporation reserved rights www com http https pdf
kb mb gb kbyte mbyte mhz khz ghz mm mil pin pins pcs pkg tm reg trademark trademarks""".split())
# 법률·안내 문구에만 나오는 낱말이 든 구절은 뺀다(데이터시트 뒷면의 면책·상표 문구)
LEGAL = set("""limitation liability liable indemnify indemnification warranty warranties merchantability purpose owners
owner respective reserves notice notices trademark trademarks property infringement license licensed licensing
damages incidental consequential arising expressly implied herein thereof whatsoever party parties provided
otherwise expand subject change changes revision history ordering information disclaimer""".split())
EDGE_STOP = set("has been even must more make use used right left high low top bottom".split())
WORD = re.compile(r"[a-z][a-z\-]*[a-z]|[a-z]")


def tokens(text: str) -> list[str]:
    return WORD.findall(text.lower())


def phrases(text: str, nmax: int = 3) -> set[str]:
    toks = tokens(text)
    out = set()
    for n in range(1, nmax + 1):
        for i in range(len(toks) - n + 1):
            g = toks[i:i + n]
            if g[0] in STOP or g[-1] in STOP or any(len(w) < 2 for w in g) or any(w in LEGAL for w in g):
                continue
            if n > 1 and (g[0] in EDGE_STOP or g[-1] in EDGE_STOP):
                continue
            if n == 1 and len(g[0]) < 4:          # 한 낱말은 4글자 이상만(약어·잡음 제외; 약어는 사전이 맡는다)
                continue
            out.add(" ".join(g))
    return out


def kicad_docs():
    """(분류 이름, 글) — 같은 분류 안에서 반복되는 설명 틀('kb flash kb')이 빈도를 부풀리지 않게 분류 단위로 센다."""
    import kicad_parts as kp
    for p in kp.default_catalog():
        yield p.get("library", ""), f"{p.get('description', '')} {p.get('keywords', '')}"


def datasheet_docs(index: str = "langchain_datasheets_v1"):
    import rag_search
    es = rag_search.es_client()
    if not es.indices.exists(index=index):
        return
    resp = es.search(index=index, size=1000, scroll="2m", source=["text", "document_id"], query={"match_all": {}})
    sid = resp.get("_scroll_id")
    while resp["hits"]["hits"]:
        for h in resp["hits"]["hits"]:
            yield h["_source"].get("document_id", ""), h["_source"].get("text", "")
        resp = es.scroll(scroll_id=sid, scroll="2m")
    es.clear_scroll(scroll_id=sid)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=500)
    ap.add_argument("--min-df", type=int, default=3)
    ap.add_argument("--no-datasheets", action="store_true")
    args = ap.parse_args()
    # 문서 빈도 = 그 구절이 나온 서로 다른 분류(KiCad) · 서로 다른 문서(데이터시트) 수
    from collections import defaultdict
    sk, sd = defaultdict(set), defaultdict(set)
    for key, t in kicad_docs():
        for ph in phrases(t):
            sk[ph].add(key)
    if not args.no_datasheets:
        for key, t in datasheet_docs():
            for ph in phrases(t):
                sd[ph].add(key)
    dk, dd = Counter({k: len(v) for k, v in sk.items()}), Counter({k: len(v) for k, v in sd.items()})
    nk = len({k for v in sk.values() for k in v}); nd = len({k for v in sd.values() for k in v})
    # 두 말뭉치의 문서 비율을 더한 점수(어느 한쪽에서만 흔한 것도 남는다). 여러 낱말 구절에 약간 가산
    score = {}
    for ph in set(dk) | set(dd):
        if dk[ph] + dd[ph] < args.min_df or (dd[ph] and dd[ph] / max(nd, 1) > 0.6 and dk[ph] == 0):
            continue   # 데이터시트 대부분에 나오고 부품 설명엔 없는 말은 상투어(저작권·주의 문구)로 본다
        n = ph.count(" ") + 1
        score[ph] = (dk[ph] / max(nk, 1) + dd[ph] / max(nd, 1)) * (1.0 + 0.5 * (n - 1))
    ranked = sorted(score, key=lambda p: -score[p])
    # 더 긴 구절이 거의 항상 함께 나오는 짧은 조각은 뺀다('rail' ⊂ 'rail-to-rail' 같은 경우는 남는다)
    keep = []
    for ph in ranked:
        if any(ph != k and ph in k and (dk[k] + dd[k]) >= 0.9 * (dk[ph] + dd[ph]) for k in keep):
            continue
        keep.append(ph)
        if len(keep) >= args.top:
            break
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8") as f:
        for ph in keep:
            f.write(json.dumps({"en": ph, "df_kicad": dk[ph], "df_datasheet": dd[ph], "words": ph.count(" ") + 1},
                               ensure_ascii=False) + "\n")
    print(f"KiCad 분류 {nk}개 · 데이터시트 문서 {nd}개 → 후보 {len(keep)}개 → {OUT.relative_to(ROOT)}")
    print("여러 낱말 구절:", sum(1 for p in keep if " " in p), "· 예:", [p for p in keep if " " in p][:12])


if __name__ == "__main__":
    main()
