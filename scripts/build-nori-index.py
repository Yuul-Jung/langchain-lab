#!/usr/bin/env python3
"""노리 사용자 사전 만들기 + 노리 문서 인덱스 만들기(기존 인덱스는 건드리지 않음).

  dict   : 출처 있는 용어를 노리로 나눠 보고, 깨지는 낱말만 static_data/nori_user_dict.txt 에 쓴다.
  index  : 새 인덱스(기본 langchain_documents_nori_v1)를 노리 하위 칸과 함께 만들고, 기존 문서 인덱스에서 복사(_reindex).
           이미 있으면 멈춘다(--replace 로만 지우고 다시 만듦).
사용: python scripts/build-nori-index.py dict
      python scripts/build-nori-index.py index [--target 이름] [--replace]
켜기: .env 에 ES_DOCUMENT_INDEX=<새 인덱스>, DOCUMENT_NORI=true 를 넣고 서버 재시작. 되돌리기: 두 줄 삭제 후 재시작.
"""
import argparse
import datetime
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import nori_dict  # noqa: E402
import rag_search  # noqa: E402
import settings  # noqa: E402


def analyze(es, word: str) -> list[dict]:
    res = es.indices.analyze(body={"tokenizer": {"type": "nori_tokenizer", "decompound_mode": "none"},
                                   "text": word, "explain": True})
    toks = res["detail"]["tokenizer"]["tokens"]
    return [{"token": t["token"], "pos": t.get("leftPOS", "").split("(")[0]} for t in toks]


def build_dict(es) -> int:
    wd, seed = nori_dict.load_sources()
    cands = nori_dict.candidate_terms(wd, seed)
    added = []
    for word in sorted(cands):
        toks = analyze(es, word)
        if nori_dict.needs_entry(toks):
            added.append((word, cands[word], "/".join(t["token"] for t in toks)))
    lines = ["# 노리 사용자 사전 (자동 생성: scripts/build-nori-index.py dict, " + datetime.date.today().isoformat() + ")",
             "# 기준: 출처 있는 용어 중 노리 기본 사전이 한 글자 조각으로 깨뜨리는 낱말만. 검색 낱말 분해용이며 뜻의 승인이 아니다.",
             "# 형식: 낱말 한 줄 (그 위 주석 줄: 출처 · 기본 분석 결과)"]
    for word, src, before in added:
        lines += [f"# {src} · 기본: {before}", word]
    nori_dict.DICT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"후보 {len(cands)}개 중 사전에 넣음 {len(added)}개 → {nori_dict.DICT_PATH.relative_to(ROOT)}")
    return 0


def build_index(es, target: str, replace: bool) -> int:
    source = settings.ES_DOCUMENT_INDEX
    if target == source:
        print("대상이 지금 쓰는 인덱스와 같습니다. 다른 이름을 쓰세요.", file=sys.stderr)
        return 1
    if es.indices.exists(index=target):
        if not replace:
            print(f"{target} 이 이미 있습니다(--replace 로만 다시 만듦).", file=sys.stderr)
            return 1
        es.indices.delete(index=target)
    mapping = es.indices.get_mapping(index=source)[source]["mappings"]
    props = mapping["properties"]
    for field in ("text", "title"):
        props[field] = {**props.get(field, {"type": "text"}), "fields": nori_dict.nori_subfield()}
    rules = nori_dict.read_rules()
    es.indices.create(index=target, settings={"analysis": nori_dict.index_analysis(rules)},
                      mappings={"properties": props})
    res = es.reindex(body={"source": {"index": source}, "dest": {"index": target}},
                     wait_for_completion=True, refresh=True)
    a, b = es.count(index=source)["count"], es.count(index=target)["count"]
    print(f"{source} → {target}: 복사 {res.get('created')}건, 실패 {len(res.get('failures', []))}건, "
          f"문서 수 {a} / {b}, 사용자 사전 {len(rules)}줄")
    return 0 if a == b and not res.get("failures") else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=["dict", "index"])
    ap.add_argument("--target", default="langchain_documents_nori_v1")
    ap.add_argument("--replace", action="store_true")
    args = ap.parse_args()
    es = rag_search.es_client()
    return build_dict(es) if args.action == "dict" else build_index(es, args.target, args.replace)


if __name__ == "__main__":
    sys.exit(main())
