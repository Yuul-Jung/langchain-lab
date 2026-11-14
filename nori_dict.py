"""노리(Elasticsearch 한국어 형태소 분석기)의 사용자 사전과 문서 인덱스 설정.

노리 기본 사전에 없는 외래 전문어는 잘게 쪼개진다(예: '레귤레이터' → 레 / 귤 / 레이터). 그러면 그 낱말로 찾을 수 없다.
사용자 사전에 넣을 낱말은 출처가 있는 용어에서만 고른다:
  - Wikidata 대응(data/ontology/ko_wikidata.jsonl) 중 대응이 맞고 분야가 전기·전자로 확인된 항목의 대표 한국어 이름·검색어
  - 한·영 후보 사전(static_data/ontology_ko_en_seed.json)의 한국어 용어 중 띄어쓰기 없는 것(용어 전체만)
넣는 기준(낱말 하나마다 노리로 먼저 나눠 본다):
  - 두 조각 이상으로 나뉘고, 그중 한 글자 조각이 있으면 깨진 것으로 보고 넣는다.
  - 두 글자 이상 조각으로만 나뉘면(예: 논리회로 → 논리 / 회로) 자연스러운 분해로 보고 넣지 않는다.
  - 조사·어미(품사 J·E)가 붙어 나뉜 것은 넣지 않는다(예: '교류를').
사전은 검색 낱말 분해에만 쓴다. 용어의 뜻·대응을 승인한 것이 아니다.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DICT_PATH = ROOT / "static_data" / "nori_user_dict.txt"
ANALYZER = "ko_nori"
_HANGUL_WORD = re.compile(r"[가-힣]{2,}")


def candidate_terms(wikidata_records: list[dict], seed_entries: list[dict]) -> dict[str, str]:
    """낱말 → 출처 설명. 한글 두 글자 이상, 띄어쓰기 없는 낱말만."""
    # 띄어 쓴 용어를 조각으로 나누지 않는다: 조각은 일반어일 수 있다(예: '저전압 강하'의 '강하' → '강하다'를 깨뜨림).
    # Wikidata 는 대응이 맞고(match) 분야가 전기·전자인 항목의 대표 이름만 쓴다(별칭은 다른 분야 말이 섞임).
    out: dict[str, str] = {}
    for r in wikidata_records:
        if r.get("domain") != "electronics" or r.get("verdict") != "match":
            continue
        for t in (r.get("term", ""), r.get("ko_label", "")):
            if _HANGUL_WORD.fullmatch(t or ""):
                out.setdefault(t, f"Wikidata {r.get('qid', '')}")
    for e in seed_entries:
        for t in e.get("ko", []):
            if _HANGUL_WORD.fullmatch(t):
                out.setdefault(t, "후보 사전(사람 승인 전)")
    return out


def needs_entry(tokens: list[dict]) -> bool:
    """tokens: 노리 분석 결과 [{'token': .., 'pos': 'NNG' ..}]. 사용자 사전에 넣어야 하면 True."""
    if len(tokens) < 2:
        return False
    if any(str(t.get("pos", "")).startswith(("J", "E")) for t in tokens):
        return False
    return any(len(t["token"]) == 1 for t in tokens)


def read_rules(path: Path = DICT_PATH) -> list[str]:
    """사전 파일에서 규칙 줄만(주석·빈 줄 제외)."""
    if not path.exists():
        return []
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")]


def index_analysis(rules: list[str]) -> dict:
    """문서 인덱스의 분석 설정: 노리 + 사용자 사전 + 품사 거르기(조사·어미 제거) + 소문자."""
    return {"analyzer": {ANALYZER: {"type": "custom", "tokenizer": "ko_nori_tok",
                                    "filter": ["nori_part_of_speech", "lowercase"]}},
            "tokenizer": {"ko_nori_tok": {"type": "nori_tokenizer", "decompound_mode": "mixed",
                                          "user_dictionary_rules": rules}}}


def nori_subfield() -> dict:
    """기존 text 칸은 그대로 두고 하위 칸 .nori 를 더한다(기존 낱말 조각 검색이 깨지지 않게)."""
    return {"nori": {"type": "text", "analyzer": ANALYZER}}


def load_sources(root: Path = ROOT) -> tuple[list[dict], list[dict]]:
    wd_path = root / "data" / "ontology" / "ko_wikidata.jsonl"
    wd = [json.loads(l) for l in wd_path.read_text(encoding="utf-8").splitlines() if l.strip()] \
        if wd_path.exists() else []
    seed = json.loads((root / "static_data" / "ontology_ko_en_seed.json").read_text(encoding="utf-8"))["entries"]
    return wd, seed
