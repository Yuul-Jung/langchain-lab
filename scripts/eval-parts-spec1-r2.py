#!/usr/bin/env python3
"""명세 1 2차 판정 도구(읽기 전용). 규칙은 static_data/verification/spec1_round2_preregistration.md.

  run    질문 파일을 기준 부품 고정(PARTS_ANCHOR_LOCK) 끔·켬으로 돌려 후보 부품을 그대로 적는다(환경이 등록한 것과 다르면 중단).
  rows   라벨 대상 대체 질문의 후보를 (부품 번호, 조건, 후보) 행으로 묶고, 설정을 가리고 섞어 라벨러용 파일과 내 쪽 열쇠 파일을 만든다.
  score  라벨 파일로 기준 1·1b·2·3·4 와 보조 지표·민감도를 계산한다.

사용: .venv/bin/python scripts/eval-parts-spec1-r2.py run --tag practice
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from collections import Counter, defaultdict
from math import comb
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
DIR = ROOT / "data" / "eval" / "spec1-r2"
PHRASE = "spec1-bundle-split-v2-emb"
ENV = {"model": "text-embedding-qwen3-embedding-4b", "dims": 2560, "es": "9.5.6", "index_docs": 22911,
       "catalog": "95fb220c783cf219", "taxonomy": "d40c1da6c01c678a", "graph": "8320b1ac0eeff43a"}
RELEVANT, WRONG, EMPTY, UNSURE = "관련 있음", "관련 없음", "빈 답", "판단 불가"


def load(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def dump(path: Path, rows: list[dict]) -> str:
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def check_env():
    import kicad_parts as kp, rag_search, settings
    es = rag_search.es_client()
    cat = kp.default_catalog()
    got = {"model": settings.EMBEDDING_MODEL, "dims": len(rag_search.embed_query("환경 점검")), "es": es.info()["version"]["number"],
           "index_docs": es.count(index="kicad_parts_v2")["count"],
           "catalog": hashlib.sha256(json.dumps(sorted(p["lib_id"] for p in cat)).encode()).hexdigest()[:16],
           "taxonomy": sha(ROOT / "static_data" / "parts_taxonomy.json"), "graph": sha(ROOT / "data" / "ontology" / "graph_ko.json")}
    bad = {k: (got[k], ENV[k]) for k in ENV if got[k] != ENV[k]}
    if bad:
        sys.exit(f"환경이 사전 등록과 다릅니다(측정 중단): {bad}")
    flags = {k: getattr(settings, k) for k in ("PARTS_SEMANTIC_SEARCH", "PARTS_CONDITIONS", "PARTS_BRIDGE", "PARTS_FUNCTION_RANK", "PARTS_GATE_ML",
                                               "PARTS_ONTOLOGY_INCLUDE_PROPOSED")}
    want = {"PARTS_SEMANTIC_SEARCH": True, "PARTS_CONDITIONS": True, "PARTS_BRIDGE": True, "PARTS_FUNCTION_RANK": False, "PARTS_GATE_ML": True,
            "PARTS_ONTOLOGY_INCLUDE_PROPOSED": False}
    if flags != want:
        sys.exit(f"서비스 설정이 사전 등록과 다릅니다(측정 중단): {flags}")
    return cat


def build(lock: bool, cat):
    import kicad_parts as kp, ontology_graph as og, parts_gate, parts_graph as pg, parts_taxonomy as pt, rag_search, settings
    g, es = og.load_graph(ROOT / "data" / "ontology" / "graph_ko.json"), rag_search.es_client()
    vecs = og.load_term_vecs(ROOT / "data" / "ontology" / "term_vecs.npz")
    deps = pg.PartsDeps(
        find=lambda q, n: kp.find_parts(q, cat, n, semantic=True, embed=rag_search.embed_query, es=es), ontology=g, include_proposed=False,
        semantic_concepts=(lambda q: og.semantic_concepts(g, q, rag_search.embed_query, vecs, include_proposed=False)) if vecs else None,
        catalog=cat, expand=True, conditions=settings.PARTS_CONDITIONS, bridge=settings.PARTS_BRIDGE, function_rank=False,
        taxonomy=pt.Taxonomy.load() if lock else None, anchor_lock=lock,
        veto=(lambda q: parts_gate.veto(q, embed=rag_search.embed_query)) if settings.PARTS_GATE_ML else None)
    return pg, pg.build_parts_graph(deps)


def cmd_run(a) -> int:
    cat = check_env()
    items = load(DIR / f"questions-{a.tag}.jsonl")
    for name, lock in (("off", False), ("on", True)):
        pg, graph = build(lock, cat)
        out = []
        for it in items:
            r = pg.ask_parts(graph, it["question"])
            parts = (r.get("parts") or [])[:5] if r["answered"] else []
            out.append({"id": it["id"], "answered": bool(r["answered"]), "abstain": r.get("abstain") or "",
                        "anchor": (r.get("anchor") or {}).get("lib_id", ""), "backend": r.get("backend") or "",
                        "scope_by": (r.get("anchor_scope") or {}).get("by", ""), "scope_function": (r.get("anchor_scope") or {}).get("function") or "",
                        "parts": [{"lib_id": p.get("lib_id", ""), "name": p.get("name", ""), "description": p.get("description", ""),
                                   "keywords": p.get("keywords", ""), "filled": bool(p.get("filled"))} for p in parts]})
        digest = dump(DIR / f"result-{a.tag}-{name}.jsonl", out)
        by = defaultdict(Counter)
        for it, r in zip(items, out):
            kind = it["kind"] + ("" if it["kind"] != "substitute" else (" 찾아짐" if it["pn_found"] else " 안 찾아짐"))
            by[kind]["답함" if r["answered"] else ("일부러 답하지 않음" if r["abstain"] else "답하지 않음")] += 1
        print(f"[{a.tag} · 고정 {name}] sha256 {digest[:16]} | " + " | ".join(f"{k}: {dict(v)}" for k, v in sorted(by.items())))
    return 0


def far_part(cat, tax, anchor_domain: str, rng: random.Random) -> dict:
    """주의 점검용: 기준 부품과 명백히 다른 기능의 부품(기준이 커넥터면 메모리, 그 밖이면 커넥터)."""
    want = "memory" if anchor_domain == "connect" else "connect"
    pool = [p for p in cat if p.get("description") and (i := tax.classify(p["library"], p["name"])) and i["domain"] == want]
    return rng.choice(pool)


def cmd_rows(a) -> int:
    import kicad_parts as kp, parts_taxonomy as pt
    cat, tax = kp.default_catalog(), pt.Taxonomy.load()
    rows: dict[tuple, dict] = {}
    for tag in a.tags:
        qs = {q["id"]: q for q in load(DIR / f"questions-{tag}.jsonl")}
        for name in ("off", "on"):
            for r in load(DIR / f"result-{tag}-{name}.jsonl"):
                q = qs[r["id"]]
                if q["kind"] != "substitute" or not q.get("label"):
                    continue
                for rank, p in enumerate(r["parts"]):
                    key = (q["pn"], q["cond"], p["lib_id"])
                    row = rows.setdefault(key, {"pn": q["pn"], "cond": q["cond"], "question": q["question"], "fn": q["fn"], "y": p, "uses": [],
                                                "check": False})
                    row["uses"].append({"id": r["id"], "tag": tag, "setting": name, "rank": rank, "filled": p["filled"]})
    rng = random.Random(hashlib.sha256(f"{PHRASE}|rows".encode()).hexdigest())
    domain = {}
    for pn in {k[0] for k in rows}:        # 주의 점검은 카탈로그에서 찾아지고 기능 영역이 정해지는 번호에만 붙인다
        group = list(kp._candidate_groups(f"{pn} 대체품", cat))
        info = tax.classify(group[0][1][0]["library"], group[0][1][0]["name"]) if group else None
        if info:
            domain[pn] = info["domain"]
    anchors = sorted({(k[0], k[1]) for k in rows if k[0] in domain})
    for pn, cond in rng.sample(anchors, min(a.checks, len(anchors))):     # 주의 점검 행: 명백히 다른 기능
        base = next(r for k, r in rows.items() if k[0] == pn and k[1] == cond)
        y = far_part(cat, tax, domain[pn], rng)
        rows[(pn, cond, "check:" + y["lib_id"])] = {"pn": pn, "cond": cond, "question": base["question"], "fn": base["fn"], "check": True, "uses": [],
                                                    "y": {"lib_id": y["lib_id"], "name": y["name"], "description": y.get("description", ""),
                                                          "keywords": y.get("keywords", ""), "filled": False}}
    order = list(rows.values())
    rng.shuffle(order)
    blind, key = [], []
    for n, r in enumerate(order, 1):
        blind.append({"row": n, "question": r["question"], "fn_hint": r["fn"], "y_number": r["y"]["name"], "y_description": r["y"]["description"],
                      "y_keywords": r["y"]["keywords"]})
        key.append({"row": n, "pn": r["pn"], "cond": r["cond"], "y_lib_id": r["y"]["lib_id"], "check": r["check"], "uses": r["uses"]})
    print(f"라벨러용 행 {len(blind)}개(주의 점검 {sum(k['check'] for k in key)}개) sha256 {dump(DIR / 'label-rows.jsonl', blind)[:16]}"
          f" | 열쇠 sha256 {dump(DIR / 'label-key.jsonl', key)[:16]}")
    lookup = DIR / "label-lookup.tsv"      # X 찾아보기 표: 번호·설명·키워드만(라이브러리 이름 없음)
    lookup.write_text("number\tdescription\tkeywords\n" + "\n".join(
        "\t".join(str(p.get(k) or "").replace("\t", " ").replace("\n", " ") for k in ("name", "description", "keywords")) for p in cat) + "\n",
        encoding="utf-8")
    print(f"찾아보기 표 {len(cat)}줄 sha256 {sha(lookup)}")
    return 0


def sign_p(b: int, c: int) -> float:
    n = b + c
    return 1.0 if n == 0 else min(1.0, 2 * sum(comb(n, k) for k in range(0, min(b, c) + 1)) / 2 ** n)


def row_class(label: dict, mode: str = "base") -> str:
    """행 라벨을 관련 있음·관련 없음(틀린 부품)·빈 답·판단 불가로. mode: base | unsure_wrong | unsure_right | strict(R2·지식 사용 → 판단 불가)."""
    lab, code, flags = label.get("label", ""), label.get("code", ""), " ".join(label.get("flags") or [])
    if lab == "관련 있음":
        cls = UNSURE if mode == "strict" and (code == "R2" or "지식 사용" in flags) else RELEVANT
        if mode == "knowledge_wrong" and "지식상 어긋남" in flags:      # 추가 민감도(라벨러 권고): 라벨러 지식으로는 어긋나는 행을 틀림으로
            cls = WRONG
    elif lab == "관련 없음":
        cls = EMPTY if code in ("E1", "E2") else WRONG
        if mode == "generic_empty" and "범용 기호" in flags:           # 추가 민감도(루브릭 v0.1 방식): 기능이 다른 범용 기호를 빈 답으로
            cls = EMPTY
    else:
        cls = UNSURE                      # 판단 불가, 해당 없음(X1), 빈 라벨
    if cls == UNSURE and mode == "unsure_wrong":
        return WRONG
    if cls == UNSURE and mode == "unsure_right":
        return RELEVANT
    return cls


def question_state(parts_cls: list[str], answered: bool) -> str:
    if not answered:
        return "못 답함"
    return "맞게 답함" if RELEVANT in parts_cls else "틀리게 답함"


def evaluate(tag: str, labels: dict[int, dict], key: list[dict], mode: str) -> dict:
    qs = {q["id"]: q for q in load(DIR / f"questions-{tag}.jsonl")}
    cls_of = {}                                  # (질문 id, 설정, 순위) → 행 분류
    for k in key:
        if k["check"]:
            continue
        c = row_class(labels.get(k["row"], {}), mode)
        for u in k["uses"]:
            if u["tag"] == tag:
                cls_of[(u["id"], u["setting"], u["rank"])] = c
    res = {name: {r["id"]: r for r in load(DIR / f"result-{tag}-{name}.jsonl")} for name in ("off", "on")}
    out = {"tag": tag, "mode": mode}
    for scope, sel in (("전체", lambda q: True), ("찾아짐", lambda q: q["pn_found"]), ("안 찾아짐", lambda q: not q["pn_found"])):
        ids = [i for i, q in qs.items() if q["kind"] == "substitute" and q.get("label") and sel(q)]
        cell = {"질문": len(ids)}
        states = {}
        for name in ("off", "on"):
            st, rows_n, wrong_rows, any_wrong, first = Counter(), 0, 0, 0, Counter()
            for i in ids:
                r = res[name][i]
                pc = [cls_of.get((i, name, k), UNSURE) for k in range(len(r["parts"]))]
                s = question_state(pc, r["answered"])
                states[(name, i)] = s
                st[s] += 1
                if s == "못 답함" and r["abstain"]:
                    st["(일부러 답하지 않음)"] += 1
                if s == "틀리게 답함":
                    st["(틀린 부품 있음)" if WRONG in pc else ("(빈 답뿐)" if EMPTY in pc else "(판단 불가뿐)")] += 1
                rows_n += len(pc)
                wrong_rows += pc.count(WRONG)
                any_wrong += bool(r["answered"] and WRONG in pc)
                if r["answered"] and pc:
                    first[pc[0]] += 1
            cell[name] = {**dict(st), "행": rows_n, "틀린 행": wrong_rows, "하나라도 틀린 질문": any_wrong, "첫 답": dict(first)}
        b = sum(1 for i in ids if states[("on", i)] == "맞게 답함" and states[("off", i)] != "맞게 답함")
        c = sum(1 for i in ids if states[("off", i)] == "맞게 답함" and states[("on", i)] != "맞게 답함")
        cell["켬만 맞음"], cell["끔만 맞음"], cell["p"] = b, c, round(sign_p(b, c), 4)
        out[scope] = cell
    ctl = [i for i, q in qs.items() if q["kind"] == "control"]
    out["대조"] = {"질문": len(ctl), **{name: sum(res[name][i]["answered"] for i in ctl) for name in ("off", "on")}}
    return out


def verdict(sealed: dict, practice: dict) -> dict:
    al, fd, ct = sealed["전체"], sealed["찾아짐"], sealed["대조"]
    ratio = lambda c: (c["틀린 행"] / c["행"]) if c["행"] else 0.0   # noqa: E731
    eff = lambda cell: 100.0 * (cell["on"].get("맞게 답함", 0) - cell["off"].get("맞게 답함", 0)) / cell["질문"] if cell["질문"] else 0.0   # noqa: E731
    v = {"1 틀리게 답함 켬≤끔": al["on"].get("틀리게 답함", 0) <= al["off"].get("틀리게 답함", 0),
         "1b 틀린 행 비율 켬≤끔": ratio(al["on"]) <= ratio(al["off"]),
         "2 대조 오처리 켬≤끔": ct["on"] <= ct["off"],
         "3 찾아짐 맞게 답함 켬>끔, p<0.05": fd["on"].get("맞게 답함", 0) > fd["off"].get("맞게 답함", 0) and fd["p"] < 0.05,
         "4 봉인 효과 ≥ 연습 효과의 절반": eff(fd) >= 0.5 * eff(practice["찾아짐"])}
    return {"기준": v, "충족": all(v.values()), "봉인 효과(찾아짐, 100개당)": round(eff(fd), 1), "연습 효과(찾아짐, 100개당)": round(eff(practice["찾아짐"]), 1),
            "틀린 행 비율": {"끔": round(ratio(al["off"]), 3), "켬": round(ratio(al["on"]), 3)}}


def cmd_score(a) -> int:
    key = load(DIR / "label-key.jsonl")
    labels = {int(x["row"]): x for x in load(a.labels)}
    checks = [k["row"] for k in key if k["check"]]
    fooled = sum(1 for r in checks if labels.get(r, {}).get("label") == "관련 있음")
    print(f"라벨 {len(labels)}행 / 행 {len(key)}개 | 주의 점검 {len(checks)}개 중 '관련 있음' {fooled}개"
          + (" → 10% 초과: 이 라벨 묶음은 쓰지 않는다" if checks and fooled / len(checks) > 0.10 else ""))
    report = {}
    for mode in ("base", "unsure_wrong", "unsure_right", "strict", "generic_empty", "knowledge_wrong"):
        s, p = evaluate("sealed", labels, key, mode), evaluate("practice", labels, key, mode)
        report[mode] = {"봉인": s, "연습": p, "판정": verdict(s, p)}
    base = report["base"]["판정"]
    flips = [m for m in ("unsure_wrong", "unsure_right", "strict") if report[m]["판정"]["충족"] != base["충족"]]
    print(json.dumps(report["base"], ensure_ascii=False, indent=1))
    print("민감도:", {m: report[m]["판정"]["기준"] for m in ("unsure_wrong", "unsure_right", "strict")})
    print("추가 민감도(사전 등록 밖):", {m: report[m]["판정"]["기준"] for m in ("generic_empty", "knowledge_wrong")})
    print("결론:", "충족" if base["충족"] else "미충족", "| 민감도에서 뒤집힘:", flips or "없음")
    (DIR / "score-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


def cmd_sample(a) -> int:
    """두 번째 라벨러용 표본: 봉인에 쓰인 행(주의 점검 제외) 중 sha256("spec1-r2-second-labeler|행 번호") 순서 앞 80개."""
    key = {k["row"]: k for k in load(DIR / "label-key.jsonl")}
    rows = [r for r in load(DIR / "label-rows.jsonl") if not key[r["row"]]["check"] and any(u["tag"] == "sealed" for u in key[r["row"]]["uses"])]
    rows.sort(key=lambda r: hashlib.sha256(f"spec1-r2-second-labeler|{r['row']}".encode()).hexdigest())
    print(f"두 번째 라벨러 표본 {len(rows[:a.n])}행(봉인 행 {len(rows)}개 중) sha256 {dump(DIR / 'label-rows-second.jsonl', rows[:a.n])[:16]}")
    return 0


def cmd_agree(a) -> int:
    first = {int(x["row"]): x for x in load(a.labels)}
    second = {int(x["row"]): x for x in load(a.second)}
    both = sorted(set(first) & set(second))
    rel = lambda x: x.get("label") == "관련 있음"   # noqa: E731
    same2 = sum(rel(first[r]) == rel(second[r]) for r in both)
    same4 = sum(first[r].get("label") == second[r].get("label") for r in both)
    table = Counter((first[r].get("label"), second[r].get("label")) for r in both)
    print(f"함께 단 행 {len(both)} | 두 갈래(관련 있음 대 그 밖) 일치 {same2} ({same2 / len(both):.1%}) | 네 갈래 일치 {same4} ({same4 / len(both):.1%})")
    print("주 라벨 → 두 번째 라벨:", {f"{k[0]} → {k[1]}": v for k, v in sorted(table.items(), key=lambda kv: -kv[1])})
    print("판정 보류 조건(두 갈래 일치 80% 미만):", "해당" if same2 / len(both) < 0.8 else "해당 없음")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run"); r.add_argument("--tag", choices=["practice", "sealed", "extra"], required=True)
    w = sub.add_parser("rows"); w.add_argument("--tags", nargs="+", default=["sealed", "practice"]); w.add_argument("--checks", type=int, default=30)
    s = sub.add_parser("score"); s.add_argument("--labels", type=Path, required=True)
    m = sub.add_parser("sample"); m.add_argument("--n", type=int, default=80)
    g = sub.add_parser("agree"); g.add_argument("--labels", type=Path, required=True); g.add_argument("--second", type=Path, required=True)
    a = ap.parse_args()
    return {"run": cmd_run, "rows": cmd_rows, "score": cmd_score, "sample": cmd_sample, "agree": cmd_agree}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
