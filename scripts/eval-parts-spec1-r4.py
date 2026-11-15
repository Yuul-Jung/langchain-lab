#!/usr/bin/env python3
"""명세 1 4차 판정 도구(읽기 전용). 규칙은 static_data/verification/spec1_round4_preregistration.md.

  run     질문 파일을 기준 부품 고정(PARTS_ANCHOR_LOCK) 끔·켬으로 돌린다. 두 쪽 모두 '카탈로그에 없음' 안내는 켠다(지금 서비스와 같게).
          환경이 등록한 것과 다르면 중단한다. 안내문은 답이 아니라 '답하지 않음(안내)'으로 적는다.
  rows    대체 질문의 후보를 (부품 번호, 조건, 후보) 행으로 묶고, 설정을 가리고 섞어 라벨러용 파일과 내 쪽 열쇠 파일을 만든다.
  sample  두 번째 라벨러용 표본(무작위 80행).
  score   라벨 파일로 기준 1·1b·2·3·4·5 와 보조 지표·민감도를 계산한다.
  agree   두 라벨러의 일치율.

사용: .venv/bin/python scripts/eval-parts-spec1-r4.py run --tag sealed
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import sys
from collections import Counter, defaultdict
from math import comb, sqrt
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
DIR = Path(os.environ.get("SPEC1_R4_DIR") or ROOT / "data" / "eval" / "spec1-r4")     # 환경 변수는 도구 점검용(가짜 낱말 목록으로 흐름 확인)
PHRASE = "spec1-bundle-split-v4"
ENV = {"model": "text-embedding-qwen3-embedding-4b", "dims": 2560, "es": "9.5.6", "index_docs": 22911,
       "catalog": "95fb220c783cf219", "taxonomy": "d40c1da6c01c678a", "graph": "8320b1ac0eeff43a"}
FLAGS = {"PARTS_SEMANTIC_SEARCH": True, "PARTS_CONDITIONS": True, "PARTS_BRIDGE": True, "PARTS_FUNCTION_RANK": False, "PARTS_GATE_ML": True,
         "PARTS_ONTOLOGY_INCLUDE_PROPOSED": False, "PARTS_UNKNOWN_NOTICE": True}
EFFECT_FLOOR = 10.6         # 기준 4: 3차 봉인 효과(+21.2/100)의 절반
RELEVANT, WRONG, EMPTY, UNSURE = "관련 있음", "관련 없음", "빈 답", "판단 불가"
MODES = ("base", "unsure_wrong", "unsure_right", "strict", "fewer_wrong")


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
    flags = {k: getattr(settings, k) for k in FLAGS}
    if flags != FLAGS:
        sys.exit(f"서비스 설정이 사전 등록과 다릅니다(측정 중단): {flags}")
    return cat


def build(lock: bool, cat):
    import kicad_parts as kp, ontology_graph as og, parts_gate, parts_graph as pg, parts_taxonomy as pt, rag_search, settings, substitute_gate
    g, es = og.load_graph(ROOT / "data" / "ontology" / "graph_ko.json"), rag_search.es_client()
    vecs = og.load_term_vecs(ROOT / "data" / "ontology" / "term_vecs.npz")
    deps = pg.PartsDeps(
        find=lambda q, n: kp.find_parts(q, cat, n, semantic=True, embed=rag_search.embed_query, es=es), ontology=g, include_proposed=False,
        semantic_concepts=(lambda q: og.semantic_concepts(g, q, rag_search.embed_query, vecs, include_proposed=False)) if vecs else None,
        catalog=cat, expand=True, conditions=settings.PARTS_CONDITIONS, bridge=settings.PARTS_BRIDGE, function_rank=False,
        taxonomy=pt.Taxonomy.load() if lock else None, anchor_lock=lock, substitute_gate=lambda q: substitute_gate.decide(q, embed=rag_search.embed_query), unknown_notice=True,
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
            notice = bool(r["answered"] and r.get("backend") == "catalog-miss")
            answered = bool(r["answered"]) and not notice
            parts = (r.get("parts") or [])[:5] if answered else []
            out.append({"id": it["id"], "answered": answered, "notice": notice, "abstain": r.get("abstain") or "",
                        "unverified": r.get("unverified") or [], "stated": bool(answered and "확인할 수 없습니다" in (r.get("answer") or "")),
                        "anchor": (r.get("anchor") or {}).get("lib_id", ""), "backend": r.get("backend") or "",
                        "scope_by": (r.get("anchor_scope") or {}).get("by", ""), "scope_function": (r.get("anchor_scope") or {}).get("function") or "",
                        "parts": [{"lib_id": p.get("lib_id", ""), "name": p.get("name", ""), "description": p.get("description", ""),
                                   "keywords": p.get("keywords", "")} for p in parts]})
        digest = dump(DIR / f"result-{a.tag}-{name}{a.suffix}.jsonl", out)
        by = defaultdict(Counter)
        for it, r in zip(items, out):
            kind = it["kind"] + ("" if it["kind"] != "substitute" else (" 찾아짐" if it["pn_found"] else " 안 찾아짐"))
            by[kind]["답함" if r["answered"] else ("안내문" if r["notice"] else ("일부러 답하지 않음" if r["abstain"] else "답하지 않음"))] += 1
        print(f"[{a.tag} · 고정 {name}] sha256 {digest[:16]} | " + " | ".join(f"{k}: {dict(v)}" for k, v in sorted(by.items())))
    return 0


def cmd_rows(a) -> int:
    import kicad_parts as kp, parts_taxonomy as pt
    cat, tax = kp.default_catalog(), pt.Taxonomy.load()
    rows: dict[tuple, dict] = {}
    qs = {q["id"]: q for q in load(DIR / "questions-sealed.jsonl")}
    for name in ("off", "on"):
        for r in load(DIR / f"result-sealed-{name}.jsonl"):
            q = qs[r["id"]]
            if q["kind"] != "substitute":
                continue
            for rank, p in enumerate(r["parts"]):
                key = (q["pn"], q["cond"], p["lib_id"])
                row = rows.setdefault(key, {"pn": q["pn"], "cond": q["cond"], "question": q["question"], "fn": q["fn"], "y": p, "uses": [], "check": False})
                row["uses"].append({"id": r["id"], "setting": name, "rank": rank})
    rng = random.Random(hashlib.sha256(f"{PHRASE}|rows".encode()).hexdigest())
    domain = {}
    for pn in {k[0] for k in rows}:        # 주의 점검은 카탈로그에서 찾아지고 기능 영역이 정해지는 번호에만 붙인다
        group = list(kp._candidate_groups(f"{pn} 대체품", cat))
        info = tax.classify(group[0][1][0]["library"], group[0][1][0]["name"]) if group else None
        if info:
            domain[pn] = info["domain"]
    pools = {want: [p for p in cat if p.get("description") and (i := tax.classify(p["library"], p["name"])) and i["domain"] == want]
             for want in ("memory", "connect")}
    anchors = sorted({(k[0], k[1]) for k in rows if k[0] in domain})
    for pn, cond in rng.sample(anchors, min(a.checks, len(anchors))):     # 주의 점검 행: 기준이 커넥터면 메모리, 그 밖이면 커넥터
        base = next(r for k, r in rows.items() if k[0] == pn and k[1] == cond)
        y = rng.choice(pools["memory" if domain[pn] == "connect" else "connect"])
        rows[(pn, cond, "check:" + y["lib_id"])] = {"pn": pn, "cond": cond, "question": base["question"], "fn": base["fn"], "check": True, "uses": [],
                                                    "y": {"lib_id": y["lib_id"], "name": y["name"], "description": y.get("description", ""),
                                                          "keywords": y.get("keywords", "")}}
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


def cmd_sample(a) -> int:
    """두 번째 라벨러용 표본 160행(주의 점검 제외, 순서는 sha256("spec1-r4-second-labeler|행 번호")).
    ① 한쪽 설정에서만 나온 행 80개 ② 나머지 80개는 주문 번호 꼴 질문의 행 30개, 처리기(MCU) 질문의 행 20개를 먼저 넣고 남는 자리를 그 밖의 행으로 채운다.
    모자라면 다음 묶음에서 채운다. 라벨러에게는 어느 묶음인지 알리지 않는다."""
    import kicad_parts as kp
    cat = kp.default_catalog()
    names = {p["name"].lower() for p in cat}
    key = {k["row"]: k for k in load(DIR / "label-key.jsonl")}
    area = {q["pn"]: q["area"] for q in load(DIR / "questions-sealed.jsonl") if q["kind"] == "substitute"}
    rows = [r for r in load(DIR / "label-rows.jsonl") if not key[r["row"]]["check"]]
    rows.sort(key=lambda r: hashlib.sha256(f"spec1-r4-second-labeler|{r['row']}".encode()).hexdigest())
    one = [r for r in rows if len({u["setting"] for u in key[r["row"]]["uses"]}) == 1]
    order_no = lambda r: key[r["row"]]["pn"].lower() not in names     # noqa: E731  카탈로그 이름과 정확히 같지 않은 번호(주문 번호 꼴·줄임 번호)
    mcu = lambda r: area.get(key[r["row"]]["pn"]) == "MCU"            # noqa: E731
    pick = one[:a.n // 2]
    rest = [r for r in rows if r not in pick]
    for group, quota in (([r for r in rest if order_no(r)], 30), ([r for r in rest if mcu(r)], 20)):
        pick += [r for r in group if r not in pick][:quota]
    pick += [r for r in rest if r not in pick][:a.n - len(pick)]
    pick = pick[:a.n]
    pick.sort(key=lambda r: hashlib.sha256(f"spec1-r4-second-labeler-order|{r['row']}".encode()).hexdigest())
    print(f"두 번째 라벨러 표본 {len(pick)}행(전체 {len(rows)}행 · 한쪽 설정에서만 나온 행 {sum(r in one for r in pick)} · 주문 번호 꼴 {sum(order_no(r) for r in pick)}"
          f" · 처리기 {sum(mcu(r) for r in pick)}) sha256 {dump(DIR / 'label-rows-second.jsonl', pick)[:16]}")
    return 0


def sign_p(b: int, c: int) -> float:
    n = b + c
    return 1.0 if n == 0 else min(1.0, 2 * sum(comb(n, k) for k in range(0, min(b, c) + 1)) / 2 ** n)


def wilson(k: int, n: int) -> str:
    if not n:
        return "0/0"
    z, p = 1.96, k / n
    d, c, half = 1 + z * z / n, p + z * z / (2 * n), z * sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return f"{k}/{n} = {100 * p:.0f}% ({100 * (c - half) / d:.0f}~{100 * (c + half) / d:.0f})"


def row_class(label: dict, mode: str = "base") -> str:
    """행 라벨을 관련 있음·관련 없음(틀린 부품)·빈 답·판단 불가로. strict: 조건 미확인(R2)·'지식 사용'·'지식상 어긋남' 행을 판단 불가로.
    fewer_wrong: 수량이 X 보다 적은 후보('수량 하향')를 틀린 부품으로."""
    lab, code, flags = label.get("label", ""), label.get("code", ""), " ".join(label.get("flags") or [])
    if lab == "관련 있음":
        cls = UNSURE if mode == "strict" and (code == "R2" or "지식 사용" in flags or "지식상 어긋남" in flags) else RELEVANT
        if mode == "fewer_wrong" and "수량 하향" in flags:
            cls = WRONG
    elif lab == "관련 없음":
        cls = EMPTY if code in ("E1", "E2") else WRONG
    else:
        cls = UNSURE                      # 판단 불가, 해당 없음(X1), 빈 라벨
    if cls == UNSURE and mode == "unsure_wrong":
        return WRONG
    if cls == UNSURE and mode == "unsure_right":
        return RELEVANT
    return cls


def evaluate(labels: dict[int, dict], key: list[dict], mode: str) -> dict:
    qs = {q["id"]: q for q in load(DIR / "questions-sealed.jsonl")}
    cls_of, code_of = {}, {}
    for k in key:
        if k["check"]:
            continue
        lab = labels.get(k["row"], {})
        for u in k["uses"]:
            cls_of[(u["id"], u["setting"], u["rank"])] = row_class(lab, mode)
            code_of[(u["id"], u["setting"], u["rank"])] = lab.get("code", "")
    res = {name: {r["id"]: r for r in load(DIR / f"result-sealed-{name}.jsonl")} for name in ("off", "on")}
    out = {"mode": mode}
    for scope, sel in (("전체", lambda q: True), ("찾아짐", lambda q: q["pn_found"]), ("안 찾아짐", lambda q: not q["pn_found"])):
        ids = [i for i, q in qs.items() if q["kind"] == "substitute" and sel(q)]
        cell, states = {"질문": len(ids)}, {}
        for name in ("off", "on"):
            st, rows_n, wrong_rows, first, codes, reasons = Counter(), 0, 0, Counter(), Counter(), Counter()
            for i in ids:
                r = res[name][i]
                pc = [cls_of.get((i, name, k), UNSURE) for k in range(len(r["parts"]))]
                s = "못 답함" if not r["answered"] else ("맞게 답함" if RELEVANT in pc else "틀리게 답함")
                states[(name, i)] = s
                st[s] += 1
                if s == "못 답함":
                    st["(안내문)" if r["notice"] else ("(일부러 답하지 않음)" if r["abstain"] else "(알아듣지 못함)")] += 1
                    if r["abstain"] and not r["notice"]:
                        reasons[r["abstain"].split(" [")[0].split("(")[0].strip()[:24]] += 1
                if s == "틀리게 답함":
                    st["(틀린 부품 있음)" if WRONG in pc else ("(빈 답뿐)" if EMPTY in pc else "(판단 불가뿐)")] += 1
                rows_n += len(pc)
                wrong_rows += pc.count(WRONG)
                codes.update(code_of.get((i, name, k), "") for k in range(len(r["parts"])))
                if r["answered"] and pc:
                    first[pc[0]] += 1
            right, wrong = st["맞게 답함"], st["틀리게 답함"]
            cell[name] = {**dict(st), "행": rows_n, "틀린 행": wrong_rows, "첫 답": dict(first), "사유": dict(sorted(codes.items())),
                          "기권 이유": dict(reasons), "정밀도": wilson(right, right + wrong), "재현율": wilson(right, len(ids))}
        b = sum(1 for i in ids if states[("on", i)] == "맞게 답함" and states[("off", i)] != "맞게 답함")
        c = sum(1 for i in ids if states[("off", i)] == "맞게 답함" and states[("on", i)] != "맞게 답함")
        cell["켬만 맞음"], cell["끔만 맞음"], cell["p"] = b, c, round(sign_p(b, c), 4)
        both = [i for i in ids if states[("off", i)] != "못 답함" and states[("on", i)] != "못 답함"]
        cell["둘 다 답한 질문"] = len(both)
        cell["켬에서 새로 틀림"] = sum(1 for i in both if states[("off", i)] == "맞게 답함" and states[("on", i)] == "틀리게 답함")
        cell["켬이 고침"] = sum(1 for i in both if states[("off", i)] == "틀리게 답함" and states[("on", i)] == "맞게 답함")
        out[scope] = cell
    ctl = [i for i, q in qs.items() if q["kind"] == "control"]
    hit = lambda r: bool(r["answered"] or r["notice"])   # noqa: E731
    out["대조"] = {"질문": len(ctl), **{name: sum(hit(res[name][i]) for i in ctl) for name in ("off", "on")},
                 "안내문": {name: sum(res[name][i]["notice"] for i in ctl) for name in ("off", "on")},
                 "켬에서 걸린 질문": [qs[i]["question"] for i in ctl if hit(res["on"][i])]}
    na = [i for i, q in qs.items() if q["kind"] == "no_anchor"]
    out["번호 없는 부품 질문"] = {"질문": len(na), **{name: sum(res[name][i]["answered"] for i in na) for name in ("off", "on")},
                           "끔은 답했는데 켬은 답하지 않음": [qs[i]["question"] for i in na if res["off"][i]["answered"] and not res["on"][i]["answered"]],
                           "답이 바뀐 질문": sum([p["lib_id"] for p in res["off"][i]["parts"]] != [p["lib_id"] for p in res["on"][i]["parts"]] for i in na)}
    return out


def verdict(s: dict) -> dict:
    al, fd, ct, na = s["전체"], s["찾아짐"], s["대조"], s["번호 없는 부품 질문"]
    ratio = lambda c: (c["틀린 행"] / c["행"]) if c["행"] else 0.0   # noqa: E731
    eff = 100.0 * (fd["on"].get("맞게 답함", 0) - fd["off"].get("맞게 답함", 0)) / fd["질문"] if fd["질문"] else 0.0
    wrong = {n: al[n].get("틀리게 답함", 0) for n in ("off", "on")}
    answered = {n: al[n].get("틀리게 답함", 0) + al[n].get("맞게 답함", 0) for n in ("off", "on")}
    rate = {n: (wrong[n] / answered[n]) if answered[n] else 0.0 for n in ("off", "on")}
    v = {"1 틀리게 답함 켬≤끔": wrong["on"] <= wrong["off"],
         "1b 틀린 행 비율 켬≤끔": ratio(al["on"]) <= ratio(al["off"]),
         "1c 둘 다 답한 질문: 새로 틀림≤고침": al["켬에서 새로 틀림"] <= al["켬이 고침"],
         "2 대조 오처리 켬≤끔": ct["on"] <= ct["off"],
         "3 찾아짐 맞게 답함 켬>끔, p<0.05": fd["on"].get("맞게 답함", 0) > fd["off"].get("맞게 답함", 0) and fd["p"] < 0.05,
         f"4 찾아짐 효과 ≥ +{EFFECT_FLOOR}/100": eff >= EFFECT_FLOOR}
    if na["질문"] >= 34:
        v["5 번호 없는 질문: 끔은 답했는데 켬은 답하지 않음 0개"] = not na["끔은 답했는데 켬은 답하지 않음"]
    small = [name for name, n, floor in (("찾아짐 질문", fd["질문"], 68), ("안 찾아짐 질문", s["안 찾아짐"]["질문"], 34), ("대조 질문", ct["질문"], 34)) if n < floor]
    return {"기준": v, "충족": all(v.values()) and not small, "칸 크기 미달": small, "찾아짐 효과(100개당)": round(eff, 1),
            "틀리게 답함의 비율(답한 것 중)": {"끔": round(rate["off"], 3), "켬": round(rate["on"], 3)},
            "기준 1(개수와 비율이 모두 나빠지지 않음)": wrong["on"] <= wrong["off"] or rate["on"] <= rate["off"],
            "틀린 행 비율": {"끔": round(ratio(al["off"]), 3), "켬": round(ratio(al["on"]), 3)}}


def cmd_score(a) -> int:
    key = load(DIR / "label-key.jsonl")
    labels = {int(x["row"]): x for x in load(a.labels)}
    checks = [k["row"] for k in key if k["check"]]
    fooled = sum(1 for r in checks if labels.get(r, {}).get("label") == "관련 있음")
    print(f"라벨 {len(labels)}행 / 행 {len(key)}개 | 주의 점검 {len(checks)}개 중 '관련 있음' {fooled}개"
          + (" → 10% 초과: 이 라벨 묶음은 쓰지 않는다" if checks and fooled / len(checks) > 0.10 else ""))
    report = {}
    for mode in MODES:
        s = evaluate(labels, key, mode)
        report[mode] = {"봉인": s, "판정": verdict(s)}
    base = report["base"]["판정"]
    # 민감도에서 '뒤집힘': 기준 1b·3·4 가 기본과 달라지거나, 기준 1 이 개수와 비율 모두에서 나빠질 때(사전 등록 5절)
    core = lambda v: [x for k, x in v["기준"].items() if k[:2] in ("1b", "1c", "3 ", "4 ")] + [v["기준 1(개수와 비율이 모두 나빠지지 않음)"]]   # noqa: E731
    want = [x for k, x in base["기준"].items() if k[:2] in ("1b", "1c", "3 ", "4 ")] + [True]
    flips = [m for m in MODES[1:] if core(report[m]["판정"]) != want]
    print(json.dumps(report["base"], ensure_ascii=False, indent=1))
    print("민감도:", {m: report[m]["판정"]["기준"] for m in MODES[1:]})
    print("결론:", "충족" if base["충족"] and not flips else "미충족", "| 민감도에서 뒤집힘(기준 1 은 개수와 비율 모두 나빠질 때):", flips or "없음")
    import part_conditions as pc
    qs = {q["id"]: q for q in load(DIR / "questions-sealed.jsonl")}
    for name in ("off", "on"):       # 확인할 수 없는 조건이 든 질문에 답하면서 그 사실을 밝혔는가(기계적으로 셈)
        res = [r for r in load(DIR / f"result-sealed-{name}.jsonl") if qs[r["id"]]["kind"] == "substitute" and r["answered"]]
        need = [r for r in res if pc.unverifiable(qs[r["id"]]["question"])]
        print(f"[{name}] 답한 대체 질문 {len(res)}개 중 확인할 수 없는 조건이 든 것 {len(need)}개, 그 사실을 밝힌 것 {sum(r['stated'] for r in need)}개")
    (DIR / (a.out or "score-report.json")).write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
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
    print("불일치 행:", [(r, first[r].get("code"), second[r].get("code")) for r in both if rel(first[r]) != rel(second[r])])
    print("판정 보류 조건(두 갈래 일치 80% 미만):", "해당" if same2 / len(both) < 0.8 else "해당 없음")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run"); r.add_argument("--tag", choices=["sealed", "extra"], required=True)
    r.add_argument("--suffix", default="", help="결과 파일 이름 끝에 붙일 글(기록된 결과를 덮어쓰지 않고 다시 돌릴 때)")
    w = sub.add_parser("rows"); w.add_argument("--checks", type=int, default=30)
    m = sub.add_parser("sample"); m.add_argument("--n", type=int, default=160)
    s = sub.add_parser("score"); s.add_argument("--labels", type=Path, required=True); s.add_argument("--out", default="")
    g = sub.add_parser("agree"); g.add_argument("--labels", type=Path, required=True); g.add_argument("--second", type=Path, required=True)
    a = ap.parse_args()
    return {"run": cmd_run, "rows": cmd_rows, "score": cmd_score, "sample": cmd_sample, "agree": cmd_agree}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
