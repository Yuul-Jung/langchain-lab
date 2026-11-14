"""Wikidata(CC0)로 한·영 용어 대응에 출처를 붙인다 — 온톨로지 한국어 층(K2).

원칙: 항목마다 '어디서 왔는지'를 남긴다. 결과는 모두 review_status = proposed (사람이 승인해야 쓴다).
두 방향:
  1) check_seed_entry : 사람이 쓴 후보 사전(static_data/ontology_ko_en_seed.json)의 한국어 용어를 Wikidata 에서 찾아,
                        그 항목의 영어 이름·별칭이 후보의 영어 키워드와 겹치는지 본다 → 후보 사전의 독립 검증.
  2) korean_for_english: 카탈로그의 영어 키워드를 Wikidata 에서 찾아, 영어 이름·별칭이 정확히 같은 항목의 한국어 이름을 가져온다.
외부로 보내는 것은 KiCad 라이브러리의 영어 용어와 후보 사전의 한국어 용어뿐이다(사용자 문서 내용은 보내지 않는다).
네트워크 호출은 Fetcher 하나로 모으고, 응답은 캐시 파일에 남겨 같은 결과를 다시 만들 수 있게 한다.
"""
from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Callable, Optional

API = "https://www.wikidata.org/w/api.php"
ITEM_URL = "https://www.wikidata.org/wiki/"
SOURCE = "Wikidata (CC0-1.0)"
REVIEW_STATUS = "proposed"
USER_AGENT = "langchain-lab-ontology/0.1 (offline research script)"   # 개인 연락처는 넣지 않는다
SEARCH_LIMIT = 5
RETRIES = 5

_TOKEN = re.compile(r"[a-z0-9]+")
_HANGUL = re.compile(r"[가-힣]")


def tokens(text: str) -> set[str]:
    return set(_TOKEN.findall((text or "").lower()))


def has_hangul(text: str) -> bool:
    return bool(_HANGUL.search(text or ""))


def _http_get(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


class Fetcher:
    """Wikidata API 호출 + 캐시. fetch 를 바꿔 끼우면 네트워크 없이 시험할 수 있다."""

    def __init__(self, cache_path: Optional[Path] = None, fetch: Callable[[str], dict] = _http_get,
                 delay: float = 2.0):
        self.cache_path = cache_path
        self.fetch = fetch
        self.delay = delay
        self.calls = 0
        self.cache: dict[str, dict] = {}
        if cache_path and cache_path.exists():
            self.cache = json.loads(cache_path.read_text(encoding="utf-8"))

    def get(self, params: dict) -> dict:
        query = urllib.parse.urlencode(sorted({**params, "format": "json"}.items()))
        if query in self.cache:
            return self.cache[query]
        if self.calls and self.delay:
            time.sleep(self.delay)                     # 공용 서비스에 부담을 주지 않도록 천천히
        self.calls += 1
        data = self._fetch_with_retry(f"{API}?{query}")
        self.cache[query] = data
        return data

    def _fetch_with_retry(self, url: str) -> dict:
        """429(너무 많음)·503(바쁨)이면 서버가 알려 준 시간(없으면 점점 길게)만큼 쉬고 다시 시도한다."""
        for attempt in range(RETRIES):
            try:
                return self.fetch(url)
            except urllib.error.HTTPError as exc:
                if exc.code not in (429, 503) or attempt == RETRIES - 1:
                    raise
                wait = exc.headers.get("Retry-After") if exc.headers else None
                time.sleep(float(wait) if wait and wait.isdigit() else 10 * (attempt + 1))
        raise RuntimeError("unreachable")

    def save(self) -> None:
        if self.cache_path:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            self.cache_path.write_text(json.dumps(self.cache, ensure_ascii=False), encoding="utf-8")


def search(fetcher: Fetcher, text: str, lang: str, limit: int = SEARCH_LIMIT) -> list[str]:
    data = fetcher.get({"action": "wbsearchentities", "search": text, "language": lang,
                        "uselang": lang, "type": "item", "limit": limit})
    return [s["id"] for s in data.get("search", []) if s.get("id")]


def entities(fetcher: Fetcher, ids: list[str]) -> dict[str, dict]:
    if not ids:
        return {}
    data = fetcher.get({"action": "wbgetentities", "ids": "|".join(ids),
                        "props": "labels|aliases|descriptions|sitelinks", "languages": "ko|en"})
    out = {}
    for qid in ids:
        e = (data.get("entities") or {}).get(qid) or {}
        if not e or "missing" in e:
            continue
        label = lambda lang: ((e.get("labels") or {}).get(lang) or {}).get("value", "")
        alias = lambda lang: [a["value"] for a in (e.get("aliases") or {}).get(lang, [])]
        out[qid] = {"qid": qid, "url": ITEM_URL + qid,
                    "ko_label": label("ko"), "ko_aliases": alias("ko"),
                    "en_label": label("en"), "en_aliases": alias("en"),
                    "en_description": ((e.get("descriptions") or {}).get("en") or {}).get("value", ""),
                    "kowiki": "kowiki" in (e.get("sitelinks") or {})}
    return out


# 분야 확인용 상위 분류(Wikidata 의 '전기·전자 장치' 계열). 항목이 이 중 하나의 하위 분류(P279*)이거나
# 그 사례(P31)이면 '전기·전자 분야'로 본다. 같은 낱말의 다른 분야 항목(무기·음반·회사 등)을 거르기 위한 것이다.
DOMAIN_ROOTS = {
    "Q11653": "electronic component", "Q3749263": "electrical device", "Q2858615": "electronic device",
    "Q175805": "semiconductor device", "Q80831": "integrated circuit", "Q167676": "sensor",
    "Q132629": "electrical circuit", "Q1815901": "electronic circuit", "Q5830907": "computer memory",
    "Q2119531": "electrical connector", "Q204157": "power supply",
}
MAX_DEPTH = 8
BATCH = 50


def _claim_ids(entity: dict, prop: str) -> set[str]:
    out = set()
    for claim in (entity.get("claims") or {}).get(prop, []):
        value = ((claim.get("mainsnak") or {}).get("datavalue") or {}).get("value")
        if isinstance(value, dict) and value.get("id"):
            out.add(value["id"])
    return out


def parent_classes(fetcher: Fetcher, ids: list[str]) -> dict[str, dict[str, set[str]]]:
    """항목마다 {'P31': 사례인 분류들, 'P279': 상위 분류들}."""
    out = {}
    for i in range(0, len(ids), BATCH):
        chunk = ids[i:i + BATCH]
        data = fetcher.get({"action": "wbgetentities", "ids": "|".join(chunk), "props": "claims"})
        for qid in chunk:
            e = (data.get("entities") or {}).get(qid) or {}
            out[qid] = {"P31": _claim_ids(e, "P31"), "P279": _claim_ids(e, "P279")}
    return out


def domain_paths(fetcher: Fetcher, qids: list[str], roots: dict = DOMAIN_ROOTS,
                 max_depth: int = MAX_DEPTH) -> dict[str, Optional[str]]:
    """항목마다 닿은 상위 분류 QID(없으면 None). 첫 걸음은 P31 또는 P279, 그다음은 P279 만 따라간다."""
    known: dict[str, dict[str, set[str]]] = {}

    def need(nodes):
        missing = sorted(n for n in nodes if n not in known)
        if missing:
            known.update(parent_classes(fetcher, missing))

    result = {}
    need(qids)
    frontiers = {q: ({q} if q in roots else known[q]["P31"] | known[q]["P279"]) for q in qids}
    seen = {q: set(f) for q, f in frontiers.items()}
    for _ in range(max_depth):
        for q, f in frontiers.items():
            if q not in result and (hit := sorted(f & roots.keys())):
                result[q] = hit[0]
        active = {q: f for q, f in frontiers.items() if q not in result and f}
        if not active:
            break
        need(set().union(*active.values()))
        for q, f in active.items():
            nxt = set().union(*(known[n]["P279"] for n in f)) - seen[q]
            seen[q] |= nxt
            frontiers[q] = nxt
        frontiers = {q: f for q, f in frontiers.items() if q not in result}
    for q, f in frontiers.items():
        if q not in result and (hit := sorted(f & roots.keys())):
            result[q] = hit[0]
    return {q: result.get(q) for q in qids}


def _record(item: dict, **extra) -> dict:
    return {**extra, **item, "source": SOURCE, "review_status": REVIEW_STATUS}


def check_seed_entry(fetcher: Fetcher, entry: dict) -> list[dict]:
    """후보 사전 한 항목의 한국어 용어마다: 일치(match) · 불일치(mismatch) · 없음(not_found) 판정."""
    want = set()
    for kw in entry.get("kw", []):
        want |= tokens(kw)
    for lib in entry.get("lib", []) + entry.get("lib_prefix", []):
        want |= tokens(lib.replace("_", " "))
    results = []
    for term in entry.get("ko", []):
        if not has_hangul(term):
            continue                                    # 'LDO' 같은 영문 약어는 한국어 검증 대상이 아니다
        found = entities(fetcher, search(fetcher, term, "ko"))
        verdict, chosen, overlap = "not_found", None, []
        for item in found.values():
            names = tokens(" ".join([item["en_label"], *item["en_aliases"]]))
            common = sorted(names & want)
            if common:
                verdict, chosen, overlap = "match", item, common
                break
        if chosen is None and found:
            verdict, chosen = "mismatch", next(iter(found.values()))
        results.append(_record(chosen or {}, term=term, direction="ko->en", verdict=verdict,
                               seed_kw=entry.get("kw", []), seed_lib=entry.get("lib", []),
                               overlap=overlap))
    return results


def korean_for_english(fetcher: Fetcher, term: str) -> Optional[dict]:
    """영어 용어와 이름·별칭이 정확히 같은(대소문자 무시) 항목 중 한국어 이름이 있는 첫 항목."""
    target = term.strip().lower()
    for item in entities(fetcher, search(fetcher, term, "en")).values():
        names = [item["en_label"], *item["en_aliases"]]
        if item["ko_label"] and any(n.strip().lower() == target for n in names):
            return _record(item, term=term, direction="en->ko", verdict="match")
    return None
