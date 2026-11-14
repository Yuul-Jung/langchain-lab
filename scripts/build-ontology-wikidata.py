#!/usr/bin/env python3
"""온톨로지 한국어 층(K2): Wikidata(CC0)로 한·영 대응에 출처(QID)를 붙인다. 결과는 모두 proposed.

  1) 후보 사전(static_data/ontology_ko_en_seed.json)의 한국어 용어 검증 (ko → en)
  2) 카탈로그에서 부품이 많이 붙은 영어 키워드의 한국어 이름 (en → ko)
출력(이 PC 전용, data/ 아래):
  data/ontology/ko_wikidata.jsonl        항목마다 용어·QID·주소·한국어/영어 이름·판정·출처
  data/ontology/wikidata_cache.json      API 응답 캐시(다시 돌리면 네트워크 없이 같은 결과)
  data/ontology/ko_wikidata_report.json  요약
외부로 보내는 것: 후보 사전의 한국어 용어와 KiCad 영어 키워드뿐(사용자 문서 내용은 보내지 않음).
사용: python scripts/build-ontology-wikidata.py [--min-parts 50] [--limit N]
"""
import argparse
import collections
import datetime
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import kicad_parts  # noqa: E402
import ontology_graph as og  # noqa: E402
import ontology_wikidata as ow  # noqa: E402

SEED = ROOT / "static_data" / "ontology_ko_en_seed.json"
OUT_DIR = ROOT / "data" / "ontology"
_SKIP = re.compile(r"\d|^.{0,2}$")   # 숫자가 든 것(모델 번호·규격 번호)과 두 글자 이하는 일반 개념이 아니다


def keyword_counts(parts) -> collections.Counter:
    c = collections.Counter()
    for p in parts:
        c.update(set(og.split_keywords(p.get("keywords", ""))))
    return c


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-parts", type=int, default=50, help="이 수 이상의 부품에 붙은 키워드만")
    ap.add_argument("--limit", type=int, default=0, help="시험용: 각 방향 최대 개수")
    args = ap.parse_args()

    fetcher = ow.Fetcher(OUT_DIR / "wikidata_cache.json")
    today = datetime.date.today().isoformat()
    records = []
    try:
        entries = json.loads(SEED.read_text(encoding="utf-8"))["entries"]
        if args.limit:
            entries = entries[:args.limit]
        for i, entry in enumerate(entries, 1):
            records += ow.check_seed_entry(fetcher, entry)
            if i % 20 == 0:
                print(f"후보 사전 {i}/{len(entries)} (호출 {fetcher.calls})", flush=True)
                fetcher.save()

        counts = keyword_counts(kicad_parts.default_catalog())
        terms = [k for k, n in counts.most_common() if n >= args.min_parts and not _SKIP.search(k)]
        if args.limit:
            terms = terms[:args.limit]
        for i, term in enumerate(terms, 1):
            r = ow.korean_for_english(fetcher, term)
            records.append(r | {"evidence_parts": counts[term]} if r else
                           {"term": term, "direction": "en->ko", "verdict": "not_found",
                            "evidence_parts": counts[term], "source": ow.SOURCE,
                            "review_status": ow.REVIEW_STATUS})
            if i % 50 == 0:
                print(f"영어 키워드 {i}/{len(terms)} (호출 {fetcher.calls})", flush=True)
                fetcher.save()
        # 분야 확인: 같은 낱말의 다른 분야 항목(무기·음반·회사 등)을 가려낸다
        qids = sorted({r["qid"] for r in records if r.get("qid")})
        print(f"분야 확인 {len(qids)}개 항목", flush=True)
        paths = ow.domain_paths(fetcher, qids)
    finally:
        fetcher.save()

    for r in records:
        r["fetched"] = today
        if r.get("qid"):
            root = paths.get(r["qid"])
            r["domain"] = "electronics" if root else "other"
            r["domain_root"] = f"{root} ({ow.DOMAIN_ROOTS[root]})" if root else ""
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with (OUT_DIR / "ko_wikidata.jsonl").open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    summary = {d: dict(collections.Counter(f'{r["verdict"]}/{r.get("domain", "-")}'
                                           for r in records if r["direction"] == d))
               for d in ("ko->en", "en->ko")}
    report = {"date": today, "source": ow.SOURCE, "min_parts": args.min_parts,
              "network_calls": fetcher.calls, "summary": summary}
    (OUT_DIR / "ko_wikidata_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1),
                                                     encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
