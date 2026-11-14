#!/usr/bin/env python3
"""DigiKey 카테고리 ↔ KiCad 분류(라이브러리) 대응표 — 보고서만 만든다(온톨로지는 바꾸지 않음, 검토 뒤 반영).

근거 두 가지:
  (A) 이름·설명 유사도: KiCad 분류 설명(읽는 이름 + 대표 키워드 + 부품 설명 3개)과 DigiKey 카테고리 경로
      ('Integrated Circuits (ICs) > Interface > Drivers, Receivers, Transceivers')를 qwen3 임베딩으로 비교 → 분류마다 상위 3개.
  (B) 실제 부품: 분류마다 대표 부품 번호 2개를 DigiKey 키워드 검색 → 그 부품이 실제로 속한 DigiKey 카테고리.
      초당 1회, 응답은 data/digikey/search_cache/ 에 저장(다시 돌리면 캐시 사용). 자격 증명은 .env, 출력하지 않는다.
판정: B 의 카테고리가 A 상위 3개 안(또는 그 조상·자손) → '강함', B 만 있음 → 'B만', A 만 → 'A만', 둘이 어긋남 → '어긋남'.
출력(git 제외): data/digikey/kicad_mapping.jsonl, data/digikey/kicad_mapping.md
사용: .venv/bin/python scripts/map-digikey-kicad.py [--skip-search] [--per-lib 2]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from pathlib import Path

import numpy as np
import requests
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
DK = ROOT / "data" / "digikey"
CACHE = DK / "search_cache"
EMB = DK / "emb_cache.json"
GENERIC_LIBS = {"Device", "Connector", "Connector_Generic", "Connector_Generic_MountingPin", "Connector_Generic_Shielded",
                "Mechanical", "Jumper", "Graphic", "power", "Simulation_SPICE", "Auxiliary_Items", "Switch"}


# ---------- DigiKey 분류 ----------
def categories():
    data = json.loads((DK / "taxonomy_raw.json").read_text(encoding="utf-8"))
    out = {}

    def walk(c, path, parent):
        cid = c.get("CategoryId")
        p = path + [c.get("Name", "")]
        out[cid] = {"id": cid, "name": c.get("Name", ""), "path": " > ".join(p), "parent": parent,
                    "count": c.get("ProductCount", 0), "depth": len(p) - 1}
        for ch in c.get("Children") or []:
            walk(ch, p, cid)
    for top in data["Categories"]:
        walk(top, [], None)
    return out


def ancestors(cats, cid):
    seen = []
    while cid is not None and cid in cats:
        seen.append(cid)
        cid = cats[cid]["parent"]
    return seen


# ---------- KiCad 분류 ----------
def kicad_libraries():
    import kicad_parts as kp
    g = json.loads((ROOT / "data" / "ontology" / "graph.json").read_text(encoding="utf-8"))
    libs = {n["label"]: n for n in g["nodes"] if n["kind"] == "library"}
    parts = {}
    for p in kp.default_catalog():
        parts.setdefault(p["library"], []).append(p)
    return libs, parts


def descriptor(lib, node, parts):
    descs = []
    for p in parts.get(lib, []):
        d = (p.get("description") or "").strip()
        if d and d not in descs:
            descs.append(d[:120])
        if len(descs) >= 3:
            break
    return f"{node.get('display_name_en', lib)}. Keywords: {', '.join(node.get('top_keywords', [])[:6])}. Examples: {'; '.join(descs)}"


MPN = re.compile(r"^[A-Z][A-Z0-9]*\d[A-Z0-9]*$")


def representative_mpns(parts, n):
    """실제 제조사 부품 번호처럼 보이는 이름(영문 대문자·숫자, 숫자 포함)을 패키지·자리표시(x) 꼬리를 떼고 고른다."""
    seen = []
    for p in sorted(parts, key=lambda p: (not p.get("datasheet"), len(p["name"]), p["name"])):
        base = re.split(r"[_]|-x|x(?=[A-Z0-9-]*$)", p["name"])[0].rstrip("-")
        if len(base) >= 4 and MPN.match(base) and base not in seen:
            seen.append(base)
        if len(seen) >= n:
            break
    return seen


# ---------- 임베딩 ----------
def embed_all(texts):
    import rag_search
    cache = json.loads(EMB.read_text()) if EMB.exists() else {}
    out = []
    for t in texts:
        k = hashlib.sha1(t.encode()).hexdigest()
        if k not in cache:
            cache[k] = rag_search.embed_query(t)
        out.append(cache[k])
    EMB.write_text(json.dumps(cache))
    m = np.array(out, dtype=np.float32)
    return m / np.linalg.norm(m, axis=1, keepdims=True)


# ---------- DigiKey 검색 ----------
class DigiKey:
    def __init__(self):
        env = dotenv_values(ROOT / ".env")
        self.cid, self.secret = env.get("DIGIKEY_CLIENT_ID"), env.get("DIGIKEY_CLIENT_SECRET")
        self.token, self.last, self.calls, self.max_calls = None, 0.0, 0, 500   # 하루 한도 1000(응답 헤더 확인) — 한 번 실행에 500회까지만

    def _token(self):
        r = requests.post("https://api.digikey.com/v1/oauth2/token", timeout=30,
                          data={"client_id": self.cid, "client_secret": self.secret, "grant_type": "client_credentials"})
        if r.status_code != 200:
            sys.exit(f"토큰 발급 실패: HTTP {r.status_code}")
        self.token = r.json()["access_token"]

    def search(self, keyword):
        CACHE.mkdir(parents=True, exist_ok=True)
        f = CACHE / (re.sub(r"[^A-Za-z0-9_-]", "_", keyword) + ".json")
        if f.exists():
            return json.loads(f.read_text())
        if self.calls >= self.max_calls:
            return {"_status": "skipped: call cap"}
        if self.token is None:
            self._token()
        self.calls += 1
        wait = 1.0 - (time.time() - self.last)
        if wait > 0:
            time.sleep(wait)
        self.last = time.time()
        r = requests.post("https://api.digikey.com/products/v4/search/keyword", timeout=30,
                          json={"Keywords": keyword, "Limit": 5, "Offset": 0},
                          headers={"Authorization": f"Bearer {self.token}", "X-DIGIKEY-Client-Id": self.cid,
                                   "X-DIGIKEY-Locale-Site": "US", "X-DIGIKEY-Locale-Language": "en",
                                   "X-DIGIKEY-Locale-Currency": "USD"})
        if r.status_code == 429:
            sys.exit("DigiKey 호출 한도에 걸렸습니다(429). 캐시가 있으니 나중에 이어서 돌리세요.")
        data = r.json() if r.status_code == 200 else {"_status": r.status_code}
        f.write_text(json.dumps(data))
        return data


def leaf_category(cat):
    """제품의 Category 에서 가장 깊은 카테고리 id."""
    while cat and cat.get("ChildCategories"):
        cat = cat["ChildCategories"][0]
    return cat.get("CategoryId") if cat else None


def product_category(data, mpn):
    prods = (data.get("ExactMatches") or []) + (data.get("Products") or [])
    for p in prods:
        num = (p.get("ManufacturerProductNumber") or "").upper()
        if num.startswith(mpn.upper()):
            return leaf_category(p.get("Category")), num
    return None, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-search", action="store_true")
    ap.add_argument("--per-lib", type=int, default=2)
    args = ap.parse_args()
    cats = categories()
    ids = list(cats)
    libs, parts = kicad_libraries()
    names = sorted(libs)
    print(f"DigiKey 카테고리 {len(ids)} · KiCad 분류 {len(names)} → 임베딩…", flush=True)
    C = embed_all([cats[i]["path"] for i in ids])
    L = embed_all([descriptor(n, libs[n], parts) for n in names])
    S = L @ C.T
    dk = None if args.skip_search else DigiKey()
    rows = []
    for li, lib in enumerate(names):
        top = [ids[j] for j in np.argsort(-S[li])[:3]]
        row = {"kicad": lib, "a_top3": [{"id": c, "path": cats[c]["path"], "sim": round(float(S[li][ids.index(c)]), 3)} for c in top],
               "generic": lib in GENERIC_LIBS, "b": []}
        if dk and lib not in GENERIC_LIBS:
            for mpn in representative_mpns(parts.get(lib, []), args.per_lib):
                cid, found = product_category(dk.search(mpn), mpn)
                row["b"].append({"mpn": mpn, "found": found, "id": cid, "path": cats.get(cid, {}).get("path") if cid else None})
        b_ids = [x["id"] for x in row["b"] if x["id"]]
        a_family = {a for c in top for a in ancestors(cats, c)} | set(top)
        agree = [b for b in b_ids if b in a_family or any(t in ancestors(cats, b) for t in top)]
        row["verdict"] = ("강함" if agree else "어긋남") if b_ids else ("일반 분류(검색 안 함)" if row["generic"] else "A만")
        row["b_ids"] = b_ids
        rows.append(row)
        if (li + 1) % 20 == 0:
            print(f"  {li + 1}/{len(names)}", flush=True)
    with (DK / "kicad_mapping.jsonl").open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    from collections import Counter
    cnt = Counter(r["verdict"] for r in rows)
    lines = ["# DigiKey ↔ KiCad 분류 대응표 (보고서, 검토 전)", "", f"판정: {dict(cnt)}", "",
             "| KiCad 분류 | 판정 | 실제 부품의 DigiKey 카테고리(B) | 이름·설명 유사도 1위(A) |", "|---|---|---|---|"]
    for r in rows:
        b = "; ".join(f"{x['mpn']} → {x['path'] or '못 찾음'}" for x in r["b"]) or "—"
        lines.append(f"| {r['kicad']} | {r['verdict']} | {b} | {r['a_top3'][0]['path']} ({r['a_top3'][0]['sim']}) |")
    (DK / "kicad_mapping.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("판정:", dict(cnt), "→ data/digikey/kicad_mapping.md")


if __name__ == "__main__":
    main()
