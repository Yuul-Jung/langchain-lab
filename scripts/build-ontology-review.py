#!/usr/bin/env python3
"""한·영 개념(168개)의 '자동 검증 단계' 시트를 만든다 — 읽기 전용, ES·LM Studio 불필요(캐시된 임베딩 사용).
입력: data/ontology/graph_ko.json, term_vecs.npz, data/eval/graph-results/parts-embed.npz, static_data/ontology_ko_en_seed.json
출력: data/ontology/review_sheet.jsonl (개념마다 한 줄) + review_sheet.md (요약 + 권고별 목록)
**이 시트는 권고일 뿐이다. approved 로 바꾸는 것은 사람(사용자)만 한다.** 개념 상태는 건드리지 않는다.

검증 항목(V1~V7)과 권고 규칙은 REPORT_RULES 에 있다."""
from __future__ import annotations
import json, sys
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import ontology_graph as og  # noqa: E402

GRAPH = ROOT / "data" / "ontology" / "graph_ko.json"
SEED = ROOT / "static_data" / "ontology_ko_en_seed.json"
OUT = ROOT / "data" / "ontology"
SAMPLE_PARTS, SAMPLE_BASE = 300, 2000

# 임계값: 분포를 본 뒤 정한 값이다(권고 보조용이며 평가 지표가 아니다). 바꾸면 시트를 다시 만든다.
MIN_PARTS = 3          # V1 근거 부품이 이보다 적으면 '보류'
BROAD_PARTS = 3000     # V4 이보다 많으면 범위가 넓어 '보류'(개념 하나가 너무 많은 부품을 가리킴)
MIN_D = 0.5            # V5 용어-부품 정합도(효과 크기)가 이보다 낮으면 '보류', 0 미만이면 '수정 필요'


# 영문 약어는 낱말 경계로만 일치하므로(예: 'led' 가 'called' 에 걸리지 않음) 대부분 안전하다.
# 위험한 것은 흔한 영어 낱말과 같은 약어(대소문자 무시로 일치)와 한 글자 한국어 용어다.
COMMON_EN = {"can", "arm", "pic", "gal", "led", "bus", "pin", "cap", "res"}
# 수정안(시드는 바꾸지 않고 여기 적어 둔다 — 합의 뒤 새 판에 반영): 개념 번호 → 더할 영어 키워드
FIX_PROPOSALS = {106: ["resistor"], 107: ["capacitor"], 108: ["inductor"], 109: ["fuse"], 110: ["crystal"], 160: ["valve"]}


def short_term(label: str) -> bool:
    ascii_only = all(ord(c) < 128 for c in label)
    core = label.replace(" ", "")
    return core.lower() in COMMON_EN if ascii_only else len(core) <= 1


def alignment(vecs, node_to_row, term_nodes, part_rows, P, base_rows):
    """용어 하나마다: 개념의 부품과의 평균 코사인 vs 무작위 부품과의 평균 코사인 → 효과 크기 d (개념 평균 기준)."""
    ds = []
    for tn in term_nodes:
        t = vecs["mat"][node_to_row[tn]]
        sc = P[part_rows] @ t
        sb = P[base_rows] @ t
        ds.append(float((sc.mean() - sb.mean()) / (sb.std() or 1.0)))
    return ds


def main():
    g = og.load_graph(GRAPH)
    seed = json.loads(SEED.read_text(encoding="utf-8"))["entries"]
    vecs = og.load_term_vecs(OUT / "term_vecs.npz")
    z = np.load(ROOT / "data" / "eval" / "graph-results" / "parts-embed.npz", allow_pickle=False)
    P, ids = z["mat"], [str(x) for x in z["ids"]]
    row_of = {lib_id: i for i, lib_id in enumerate(ids)}
    node_to_row = {n: i for i, n in enumerate(vecs["nodes"])}
    rng = np.random.default_rng(7)
    base_rows = rng.choice(len(ids), SAMPLE_BASE, replace=False)
    rows = []
    for i, e in enumerate(seed):
        c = f"concept:{i}"
        if c not in g:
            continue
        nb = list(g.neighbors(c))
        term_nodes = [n for n in nb if g.nodes[n].get("kind") == "term"]
        kws = sorted(g.nodes[n]["label"] for n in nb if g.nodes[n].get("kind") == "keyword")
        libs = sorted(g.nodes[n]["label"] for n in nb if g.nodes[n].get("kind") == "library")
        missing_kw = [k for k in e.get("kw", []) if k not in kws]
        parts = og.concept_parts(g, c, limit=10 ** 6)
        flags, fatal = [], []
        if not parts:
            fatal.append("근거 부품 0개")
        elif len(parts) < MIN_PARTS:
            flags.append(f"근거 부품 {len(parts)}개(적음)")
        if len(parts) > BROAD_PARTS:
            flags.append(f"범위 넓음({len(parts)}개)")
        if missing_kw:
            fatal.append(f"카탈로그에 없는 키워드 {missing_kw}")
        shorts = [g.nodes[t]["label"] for t in term_nodes if short_term(g.nodes[t]["label"])]
        if shorts:
            flags.append(f"짧은 용어(오탐 위험) {shorts}")
        d_mean = d_best = None
        if parts:
            idx = [row_of[p["lib_id"]] for p in parts if p["lib_id"] in row_of]
            if len(idx) > SAMPLE_PARTS:
                idx = list(rng.choice(idx, SAMPLE_PARTS, replace=False))
            ds = alignment(vecs, node_to_row, [t for t in term_nodes if t in node_to_row], idx, P, base_rows) if idx else []
            if ds:
                d_mean, d_best = float(np.mean(ds)), float(max(ds))
                if d_best < 0:
                    fatal.append(f"용어-부품 정합도 음수({d_best:.2f})")
                elif d_best < MIN_D:
                    flags.append(f"용어-부품 정합도 낮음({d_best:.2f})")
        wd = g.nodes[c].get("wikidata_supported_terms", 0)
        rec = "수정 필요" if fatal else ("보류" if flags else "권고 승인")
        fix = FIX_PROPOSALS.get(i)
        rows.append({"concept_id": c, "index": i, "ko": e["ko"], "kw": kws, "lib": libs, "lib_prefix": e.get("lib_prefix", []),
                     "evidence_parts": len(parts), "example_parts": [p["lib_id"] for p in parts[:3]],
                     "alignment_best": None if d_best is None else round(d_best, 3),
                     "alignment_mean": None if d_mean is None else round(d_mean, 3),
                     "wikidata_supported_terms": wd, "flags": flags, "fatal": fatal, "recommendation": rec,
                     "fix_proposal": {"add_kw": fix} if fix else None,
                     "review_status": g.nodes[c].get("review_status")})
    (OUT / "review_sheet.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    cnt = {k: sum(1 for r in rows if r["recommendation"] == k) for k in ("권고 승인", "보류", "수정 필요")}
    ds_all = [r["alignment_best"] for r in rows if r["alignment_best"] is not None]
    md = ["# 한·영 개념 자동 검증 시트", "",
          "**권고일 뿐이며 approved 는 사람(사용자)만 정한다.** 모든 개념의 현재 상태는 proposed 이다.", "",
          f"- 개념 {len(rows)}개 → 권고 승인 {cnt['권고 승인']} · 보류 {cnt['보류']} · 수정 필요 {cnt['수정 필요']}",
          f"- 용어-부품 정합도(d, 효과 크기) 분포: 최소 {min(ds_all):.2f} · 중앙 {float(np.median(ds_all)):.2f} · 최대 {max(ds_all):.2f}",
          "", "## 검증 항목과 규칙",
          "- V1 근거 부품 수(0개 → 수정 필요, 3개 미만 → 보류) · V2 카탈로그에 없는 키워드(→ 수정 필요)",
          "- V3 오탐 위험 용어(한국어 1글자, 또는 흔한 영어 낱말과 같은 영문 약어 can·arm·pic·gal·led 등 → 보류). 규칙 변경 1회 기록: 처음에는 영문 3자 이하를 모두 보류로 했으나, 영문은 낱말 경계로만 일치해 위험이 낮아 흔한 영어 낱말만 남김(동료 독립 검토 전에 변경)",
          f"- V4 범위가 너무 넓음(부품 {BROAD_PARTS}개 초과 → 보류) · V5 용어와 개념 부품의 임베딩 정합도(무작위 부품 대비 효과 크기 d, {MIN_D} 미만 → 보류, 0 미만 → 수정 필요)",
          "- V6 Wikidata 지원 용어 수(정보용, 승인 대용 아님) · V7 사람 승인(이 시트 밖: 사용자)",
          f"- 임계값(MIN_PARTS={MIN_PARTS}, BROAD_PARTS={BROAD_PARTS}, MIN_D={MIN_D})은 분포를 본 뒤 정했다 — 권고 보조용이며 성능 지표가 아니다."]
    for k in ("수정 필요", "보류", "권고 승인"):
        md += ["", f"## {k} ({cnt[k]})"]
        for r in rows:
            if r["recommendation"] == k:
                why = "; ".join(r["fatal"] + r["flags"]) or "—"
                if r["fix_proposal"]:
                    why += f" | 수정안: 키워드 {r['fix_proposal']['add_kw']} 추가"
                md.append(f"- #{r['index']} {' / '.join(r['ko'][:3])} → {','.join(r['lib'][:2]) or ','.join(r['kw'][:2])} "
                          f"(부품 {r['evidence_parts']}, d {r['alignment_best']}, Wikidata {r['wikidata_supported_terms']}) {why}")
    (OUT / "review_sheet.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"개념 {len(rows)}개 → 권고 승인 {cnt['권고 승인']} · 보류 {cnt['보류']} · 수정 필요 {cnt['수정 필요']}")
    print("정합도 d 분포 사분위:", [round(float(np.percentile(ds_all, q)), 2) for q in (0, 10, 25, 50, 75, 90, 100)])


if __name__ == "__main__":
    main()
