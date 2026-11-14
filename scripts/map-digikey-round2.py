#!/usr/bin/env python3
"""분류 대응 2차: 1차에서 '검토 필요(proposed)'로 남은 KiCad 분류에 실제 부품 증거를 더 모아 같은 규칙으로 다시 판정한다.

71 의 독립 검토 답(best)은 바꾸지 않는다. 추가하는 것은 DigiKey 에서 본 실제 부품(분류마다 다음 3개)뿐이다.
판정 규칙(실행 전에 고정, 2026-11-15) — 하나라도 만족하면 approved:
  R1(1차 그대로) best 가 이름 유사도 1위
  R2(1차 그대로, 부품 수만 늘림) 실제 부품의 분류 중 이름 유사도 상위 3개와 같은 가족(조상·자손)인 것이 best 와 같음
  R3(새 규칙, 부품 수가 늘어서 가능) 찾은 부품이 3개 이상이고, 그 중 60% 이상이 best 이거나 그 하위 분류에 있음
아니면 proposed 로 남긴다. 규칙은 결과를 본 뒤 바꾸지 않는다.
호출: 키워드 검색 1회/부품, 캐시 공유, 한 번 실행 상한 --max-calls(기본 150). 부품 번호만 보낸다.
출력(git 제외): data/digikey/kicad_mapping_approved_r2.jsonl (1차 파일은 그대로 둔다)
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from collections import Counter
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location("mapdk", ROOT / "scripts" / "map-digikey-kicad.py")
mapdk = importlib.util.module_from_spec(spec); spec.loader.exec_module(mapdk)
DK = ROOT / "data" / "digikey"
APPROVER = "delegated: jung-29 + 71 (사용자 위임)"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-calls", type=int, default=150)
    ap.add_argument("--extra", type=int, default=3)
    args = ap.parse_args()
    cats = mapdk.categories()
    libs, parts = mapdk.kicad_libraries()
    r1 = [json.loads(l) for l in (DK / "kicad_mapping_approved.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    base = {json.loads(l)["kicad"]: json.loads(l) for l in (DK / "kicad_mapping.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()}
    dk = mapdk.DigiKey(); dk.max_calls = args.max_calls
    out, cnt = [], Counter()
    for row in r1:
        if row["decision"] != "proposed":
            out.append(row); continue
        lib, best = row["kicad"], row["digikey_id"]
        b = base[lib]
        mpns = mapdk.representative_mpns(parts.get(lib, []), 2 + args.extra)[2:]    # 1차에서 쓴 앞 2개 다음 것
        new_b = []
        for mpn in mpns:
            data = dk.search(mpn)
            if data.get("_status") == "skipped: call cap":
                break
            cid, found = mapdk.product_category(data, mpn)
            if cid:
                new_b.append(cid)
        b_all = list(b["b_ids"]) + new_b
        top3 = [a["id"] for a in b["a_top3"]]
        fam = lambda c: set(mapdk.ancestors(cats, c))
        a_family = {x for t in top3 for x in fam(t)}
        r1ok = best == top3[0]
        r2ok = any(x == best and (x in a_family or any(t in fam(x) for t in top3)) for x in b_all)
        under = [x for x in b_all if best in fam(x)]                       # best 이거나 그 하위 분류
        r3ok = len(b_all) >= 3 and len(under) / len(b_all) >= 0.6
        d = "approved" if (r1ok or r2ok or r3ok) else "proposed"
        cnt[d] += 1
        out.append({**row, "decision": d, "round": 2, "b_found_total": len(b_all), "b_under_best": len(under),
                    "rule": "R1" if r1ok else "R2" if r2ok else "R3" if r3ok else "-",
                    "approver": APPROVER if d == "approved" else "-", "date": date.today().isoformat(),
                    "reason": (row.get("reason") or "") + f" | 2차: 실제 부품 {len(b_all)}개 중 best 아래 {len(under)}개"})
    with (DK / "kicad_mapping_approved_r2.jsonl").open("w", encoding="utf-8") as f:
        for o in out:
            f.write(json.dumps(o, ensure_ascii=False) + "\n")
    tot = Counter(o["decision"] for o in out)
    print("API 호출", dk.calls, "| 2차에서 바뀐 것", dict(cnt), "| 전체", dict(tot))


if __name__ == "__main__":
    main()
