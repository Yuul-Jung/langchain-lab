#!/usr/bin/env python3
"""DigiKey Product Information V4 — 전체 카테고리(분류 체계) 조회. 읽기 전용, KiCad 분류와 맞대기 위한 원자료.

자격 증명: .env 의 DIGIKEY_CLIENT_ID / DIGIKEY_CLIENT_SECRET (git 제외 파일, 화면·로그에 출력하지 않는다).
결과(git 제외): data/digikey/taxonomy_raw.json(원본), data/digikey/taxonomy_raw.csv(계층 평탄화)
실행: .venv/bin/python scripts/fetch-digikey-categories.py
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import requests
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "digikey"
TOKEN_URL = "https://api.digikey.com/v1/oauth2/token"
CATEGORIES_URL = "https://api.digikey.com/products/v4/search/categories"


def credentials():
    env = dotenv_values(ROOT / ".env")
    cid, secret = env.get("DIGIKEY_CLIENT_ID"), env.get("DIGIKEY_CLIENT_SECRET")
    if not cid or not secret:
        sys.exit(".env 에 DIGIKEY_CLIENT_ID / DIGIKEY_CLIENT_SECRET 가 없습니다.")
    return cid, secret


def token(cid, secret):
    r = requests.post(TOKEN_URL, timeout=30, data={"client_id": cid, "client_secret": secret,
                                                   "grant_type": "client_credentials"})
    if r.status_code != 200:   # 응답 본문에 계정 정보가 섞일 수 있어 상태 코드만 보인다
        sys.exit(f"토큰 발급 실패: HTTP {r.status_code}")
    return r.json()["access_token"]


def flatten(cat, rows, parent_id="", parent_name="", depth=0):
    cid = cat.get("CategoryId") or cat.get("Id") or ""
    name = cat.get("Name") or ""
    rows.append({"depth": depth, "CategoryId": cid, "Name": name, "ParentId": parent_id, "ParentName": parent_name,
                 "ProductCount": cat.get("ProductCount", "")})
    for child in cat.get("Children") or cat.get("children") or []:
        flatten(child, rows, cid, name, depth + 1)


def main():
    cid, secret = credentials()
    print("▶ 토큰 요청…")
    tok = token(cid, secret)
    print("▶ 카테고리 조회…")
    r = requests.get(CATEGORIES_URL, timeout=60, headers={
        "Authorization": f"Bearer {tok}", "X-DIGIKEY-Client-Id": cid,
        "X-DIGIKEY-Locale-Site": "US", "X-DIGIKEY-Locale-Language": "en", "X-DIGIKEY-Locale-Currency": "USD"})
    if r.status_code != 200:
        sys.exit(f"카테고리 조회 실패: HTTP {r.status_code}")
    data = r.json()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "taxonomy_raw.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    cats = data.get("Categories") or data.get("categories") or (data if isinstance(data, list) else None)
    if not cats:
        sys.exit(f"예상한 키가 없습니다. 최상위 키: {list(data)[:10]} (taxonomy_raw.json 확인)")
    rows: list[dict] = []
    for top in cats:
        flatten(top, rows)
    with (OUT / "taxonomy_raw.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    depth = {}
    for row in rows:
        depth[row["depth"]] = depth.get(row["depth"], 0) + 1
    print(f"✓ 저장: {OUT.relative_to(ROOT)}/taxonomy_raw.json, taxonomy_raw.csv — 전체 {len(rows)}개, 깊이별 {depth}")
    print("최상위 카테고리:")
    for row in rows:
        if row["depth"] == 0:
            print(f"  [{row['CategoryId']:>5}] {row['Name']}  ({row['ProductCount']})")


if __name__ == "__main__":
    main()
