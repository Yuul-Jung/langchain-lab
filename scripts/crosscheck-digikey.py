#!/usr/bin/env python3
"""S1 DigiKey 교차 확인: KiCad 부품 값과 DigiKey 값을 부품마다 맞대고, S2 부품 기록(part_record)으로 남긴다.

표본(결정적): (1) 정답 세트 부품(--gold, lib_id 목록 파일) 전부 + (2) 일반 분류를 뺀 분류마다 3개(seed 0, sha1 순서).
DigiKey 부품 번호 고르기(기록함 — 이 고르기 자체가 오차 원인):
  KiCad 이름에서 '_' 뒤(패키지)를 떼고, 첫 소문자 x(자리표시) 앞까지를 검색어로 → 정확히 일치(ExactMatches) 우선,
  없으면 검색어로 시작하는 첫 제품. 못 찾으면 '못 찾음'.
비교 항목: 핀 수(KiCad pin_count ↔ DigiKey 패키지 글자), 패키지 계열(KiCad 풋프린트 ↔ DigiKey Package/Case),
  전원 전압·동작 온도(DigiKey 값만 — KiCad 설명은 입력·출력 전압이 섞여 있어 쓰지 않음), DigiKey 카테고리.
출력(git 제외): data/parts_records/records.jsonl, data/parts_records/s1_report.json
호출: 키워드 검색 1회/부품(응답에 매개변수 포함), 캐시 data/digikey/search_cache 공유, 한 번 실행 상한 --max-calls.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import sys
from collections import Counter
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import part_record as pr  # noqa: E402

spec = importlib.util.spec_from_file_location("mapdk", ROOT / "scripts" / "map-digikey-kicad.py")
mapdk = importlib.util.module_from_spec(spec); spec.loader.exec_module(mapdk)
OUT = ROOT / "data" / "parts_records"


def query_for(name: str) -> tuple[str, str]:
    base = name.split("_")[0]
    rule = "패키지 꼬리 뗌" if "_" in name else "이름 그대로"
    m = re.search(r"x", base)
    if m and m.start() >= 3:
        base, rule = base[:m.start()], rule + " + 자리표시 x 앞까지"
    return base.rstrip("-"), rule


def pick(data: dict, q: str):
    exact = data.get("ExactMatches") or []
    if exact:
        return exact[0], "정확히 일치"
    for p in data.get("Products") or []:
        if (p.get("ManufacturerProductNumber") or "").upper().startswith(q.upper()):
            return p, "검색어로 시작"
    return None, "못 찾음"


def params(p: dict) -> dict:
    return {x.get("ParameterText"): x.get("ValueText") for x in p.get("Parameters") or []}


def sample(libs, parts, gold_ids, per_lib=3, seed=0):
    out, seen = [], set()
    by_id = {p["lib_id"]: p for ps in parts.values() for p in ps}
    for g in gold_ids:
        if g in by_id:
            out.append((by_id[g], True)); seen.add(g)
    for lib in sorted(libs):
        if lib in mapdk.GENERIC_LIBS:
            continue
        cand = sorted(parts.get(lib, []), key=lambda p: hashlib.sha1(f"{seed}:{p['lib_id']}".encode()).hexdigest())
        for p in cand[:per_lib]:
            if p["lib_id"] not in seen:
                out.append((p, False)); seen.add(p["lib_id"])
    return out


def record(part, dk_product, dk_rule, q, q_rule, today, cats, variants=()):
    ref = part["lib_id"]
    fields = {}
    kpins = part.get("pin_count") or None
    kpkg = pr.package_family(part.get("footprint") or "") or pr.package_family(part.get("description") or "")
    ev = {"pin_count": [pr.evidence("kicad", kpins, ref, today, unit="pins", typ=kpins) if kpins else None],
          "package": [pr.evidence("kicad", kpkg, ref, today) if kpkg else None],
          "supply_voltage": [], "operating_temperature": [], "category": []}
    mpn = None
    if dk_product:
        mpn = dk_product.get("ManufacturerProductNumber")
        P = params(dk_product)
        pkg_text = P.get("Package / Case") or P.get("Supplier Device Package") or ""
        dpins = pr.pins_from_package(pkg_text) or pr.pins_from_package(P.get("Supplier Device Package") or "")
        if dpins:
            ep = bool(re.search(r"exposed pad|\bEP\b", pkg_text, re.I))   # KiCad 는 노출 패드를 핀 하나로 센다
            n = dpins + 1 if ep else dpins
            ev["pin_count"].append(pr.evidence("digikey", n, mpn, today, unit="pins", typ=n,
                                               conditions="노출 패드 포함(+1)" if ep else ""))
        dpkg = pr.package_family(pkg_text) or pr.package_family(P.get("Supplier Device Package") or "")
        if dpkg:
            ev["package"].append(pr.evidence("digikey", dpkg, mpn, today, conditions=pkg_text))
        # 같은 검색어의 주문 가능한 변형(제조사·등급·포장)마다 값을 모은다. 서로 다르면 모두 근거로 남겨 충돌로 드러낸다(하나를 고르지 않음)
        for key, field, unit in (("Voltage - Supply", "supply_voltage", "V"), ("Operating Temperature", "operating_temperature", "°C")):
            seen = {}
            for v in [dk_product] + [x for x in variants if x is not dk_product]:
                vp = params(v)
                text = next((t for k, t in vp.items() if k and k.startswith(key)), None)
                lo, hi = pr.parse_range(text or "", unit)
                if lo is None:
                    continue
                single = lo == hi and not re.search(r"~|\bto\b|\.\.|–", text or "")
                k = ("single", lo) if single else (lo, hi)
                seen.setdefault(k, (text, v.get("ManufacturerProductNumber"), single))
            for (a, b), (text, num, single) in seen.items():
                if single:   # 'Voltage - Supply: 2.7 V' 처럼 값 하나 — 최소인지 최대인지 알 수 없으니 범위로 쓰지 않는다
                    ev[field].append(pr.evidence("digikey", text, num, today, unit=unit, conditions="단일 값(범위 아님)"))
                else:
                    ev[field].append(pr.evidence("digikey", text, num, today, unit=unit, lo=a, hi=b,
                                                 conditions=f"변형 {len(seen)}종 중" if len(seen) > 1 else ""))
        cid = mapdk.leaf_category(dk_product.get("Category"))
        if cid:
            ev["category"].append(pr.evidence("digikey", cats.get(cid, {}).get("path", str(cid)), mpn, today))
    for f, evs in ev.items():
        fields[f] = pr.resolve(evs)
    return {"lib_id": ref, "query": q, "query_rule": q_rule, "digikey_mpn": mpn, "pick_rule": dk_rule, "fields": fields}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gold", default="")
    ap.add_argument("--max-calls", type=int, default=400)
    args = ap.parse_args()
    gold = [l.strip() for l in Path(args.gold).read_text().splitlines() if l.strip()] if args.gold else []
    cats = mapdk.categories()
    libs, parts = mapdk.kicad_libraries()
    todo = sample(libs, parts, gold)
    dk = mapdk.DigiKey(); dk.max_calls = args.max_calls
    today = date.today().isoformat()
    OUT.mkdir(parents=True, exist_ok=True)
    recs, skipped = [], 0
    for part, is_gold in todo:
        q, q_rule = query_for(part["name"])
        data = dk.search(q)
        if data.get("_status") == "skipped: call cap":
            skipped += 1; continue
        prod, rule = pick(data, q)
        # 변형: 검색어가 부품 번호 안에 들어 있는 것(앞의 제조사 접두어 SN·CD·MC 허용, 뒤에 숫자가 바로 이어지면 다른 부품)
        vpat = re.compile(r"(?<![A-Z0-9])(?:[A-Z]{1,3})?" + re.escape(q.upper()) + r"(?![0-9])")
        variants = [x for x in (data.get("ExactMatches") or []) + (data.get("Products") or [])
                    if vpat.search((x.get("ManufacturerProductNumber") or "").upper())] if prod else []
        r = record(part, prod, rule, q, q_rule, today, cats, variants)
        r["gold"] = is_gold
        recs.append(r)
    with (OUT / "records.jsonl").open("w", encoding="utf-8") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    rep = {"sampled": len(todo), "checked": len(recs), "skipped_by_call_cap": skipped, "api_calls_this_run": dk.calls,
           "found": sum(1 for r in recs if r["digikey_mpn"]), "pick_rule": dict(Counter(r["pick_rule"] for r in recs)),
           "fields": {f: dict(Counter(r["fields"][f]["status"] for r in recs)) for f in pr.FIELDS}}
    (OUT / "s1_report.json").write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(rep, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
