#!/usr/bin/env python3
"""명세 1 질문 세트 생성기(결정적). 정의: static_data/verification/spec1_parts_search.md · spec1_split_plan.md.

규칙 파일(parts_graph·ontology 등)을 보지 않고 spec1_lexicon.py 의 낱말과 문장 틀만 쓴다. 정답 = 카탈로그 라이브러리 이름(gold_libs, KiCad 디렉터리 구조).
출력(이 PC 전용 data/eval/spec1/): questions-{practice,sealed}.jsonl(정답·메타 포함), label-input-sealed.jsonl(id·질문만, 98 라벨용, 순서 섞음).
사용: python3 verification/gen_questions_spec1.py
"""
from __future__ import annotations

import hashlib
import json
import random
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import spec1_lexicon as L  # noqa: E402

ROOT = HERE.parent
OUT = ROOT / "data" / "eval" / "spec1"
PHRASE = "spec1-bundle-split-v1"
SEED = "spec1-gen-v1"
D = list(L.D_ITEMS)
B = ["B1", "B2", "B3", "B4", "B5"]
EH = ["E1", "E2", "E3", "E4", "E5"]
hs = lambda n: hashlib.sha256(f"{PHRASE}|{n}".encode()).hexdigest()  # noqa: E731


def sealed_sets():
    pb = [f"{d}|{b}" for d in D for b in B]
    eb = [f"{e}|{b}" for e in EH for b in B]
    po, eo = sorted(pb, key=hs), sorted(eb, key=hs)
    return set(po[0:18]), set(eo[10:18])  # spec1_split_plan.md 에 기록된 창(0, 10)


def rng_for(*keys) -> random.Random:
    return random.Random(hashlib.sha256(("|".join(map(str, keys)) + SEED).encode()).hexdigest())


KINDS = {"power": "vpo", "analog": "vpo", "logic": "vpo", "mcu_mem": "vpi", "comm_rf": "vpi", "sensor": "vpi", "drive_em": "vpo", "discrete": "vpo",
         "passive_conn": "p", "module": "vio", "other_mixed": "vp"}  # 항목 영역에 어울리는 조건 종류만(조건은 채점하지 않으며 문장 자연스러움을 위해)


def cond_text(rng: random.Random, level: int, short: bool, d: str) -> tuple[str, int]:
    """조건 수 level 만큼 서로 다른 종류에서 고른 수식어(공백 구분). short 면 각 조건의 첫 낱말만(B1 ≤4 낱말용)."""
    kinds = list(KINDS[d])
    rng.shuffle(kinds)
    parts = []
    for k in kinds[:level]:
        t = rng.choice(L.COND[k])
        parts.append(t.split()[0] if short else t)
    return " ".join(parts), len(parts)


def nwords(q: str) -> int:
    return len(q.split())


_CAT = None


def pn_in_catalog(pn: str) -> bool:
    """부품 이름이 카탈로그 이름·설명에 있는지(보고용: 없는 이름의 대체 질문은 처리 못함이 설계상 자연스러움)."""
    global _CAT
    if _CAT is None:
        sys.path.insert(0, str(ROOT))
        import kicad_parts as kp  # noqa: E402
        _CAT = "\n".join(f"{p.get('name', '')} {p.get('description', '')}" for p in kp.parts_catalog()).lower()
    return pn.lower().split()[0] in _CAT


def lib_leak(q: str, libs: list[str]) -> bool:
    """질문에 정답 라이브러리 이름의 영어 낱말(길이≥4)이 들어 있으면 순환 위험(검색이 라이브러리 이름과 글자로 맞춤)."""
    ql = q.lower()
    for lib in libs:
        for tok in re.split(r"[_/ ]+", lib.lower()):
            if len(tok) >= 4 and not tok.isdigit() and re.search(r"(?<![a-z0-9])" + re.escape(tok) + r"(?![a-z0-9])", ql):
                return True
    return False


# ---------- 의도별 문장 틀 ----------
def a1(b, it, c, rng):
    c = c + " " if c else ""
    f = {"B1": [f"{c}{it['ko']}", f"{c}{it['ko']} 칩", f"{c}{rng.choice(it['v'])}"],
         "B2": [f"{c}{it['ko']} 찾아줘", f"{c}{it['ko']} 부품 추천해줘", f"{c}{it['ko']} 골라줘"],
         "B3": [f"{c}{it['ko']} 쪽으로 회로를 설계 중인데 어떤 부품이 좋을까요?", f"{c}{it['ko']} 필요한 보드를 만들고 있어요, 어떤 걸 쓰면 될까요?"],
         "B4": [f"{c}{it['en']} 추천", f"{c}{it['en']} 부품 찾아줘", f"{c}{it['en']} 어떤 게 좋아?"],
         "B5": [f"{c}{rng.choice(it['v'])}", f"{c}{rng.choice(it['v'])} 찾아줘", f"{c}{rng.choice(it['v'])}추천"]}
    return rng.choice(f[b])


def a2(b, it, c, rng):
    pn = rng.choice(it["pn"])
    c = c + " " if c else ""
    f = {"B1": [f"{pn} 대체품", f"{c}{pn} 비슷한 칩", f"{pn} 말고 다른 거"],
         "B2": [f"{pn} 대체할 수 있는 {c}부품 찾아줘", f"{c}{pn} 비슷한 부품 추천해줘"],
         "B3": [f"{pn} 단종이라는데 {c}비슷한 부품으로 바꾸려면 뭘 골라야 할까요?", f"{pn} 구하기 어려워서 {c}다른 걸로 바꾸고 싶은데 추천해 주세요."],
         "B4": [f"{pn} drop-in replacement {c}추천", f"{pn} alternative part {c}찾아줘"],
         "B5": [f"{pn}대체품", f"{pn.lower()} 대체가능한거", f"{pn}말고 비슷한거"]}
    return rng.choice(f[b]), pn


def a3(b, it1, it2, c, rng):
    c = c + " " if c else ""
    k1, k2 = it1["ko"], it2["ko"]
    v1, v2 = rng.choice(it1["v"]), rng.choice(it2["v"])
    f = {"B1": [f"{c}{v1} {v2} 조합", f"{c}{v1}, {v2} 같이"],
         "B2": [f"{c}{k1}, {k2} 둘 다 필요한데 부품 추천해줘", f"{c}{k1}하고 {k2} 같이 쓸 부품 찾아줘"],
         "B3": [f"한 보드에 {c}{k1}, {k2} 둘 다 넣으려는데 각각 어떤 부품이 좋을까요?"],
         "B4": [f"{c}{it1['en']} + {it2['en']} 조합 부품 추천", f"{c}{it1['en']} and {it2['en']} 같이 필요해"],
         "B5": [f"{c}{v1}랑{v2}", f"{c}{v1} {v2} 같이 필요", f"{c}{v1}하고{v2} 추천"]}
    return rng.choice(f[b])


def a4(b, it, c, rng):
    pn = rng.choice(it["pn"])
    f = {"B1": [f"{pn} 뭐하는 부품", f"{pn} 용도"], "B2": [f"{pn} 어떤 부품인지 설명해줘", f"부품 {pn} 설명 좀 해줘"],
         "B3": [f"{pn}이라는 부품이 있던데 어떤 역할을 하는 건가요?", f"{pn} 부품이 회로에서 하는 일이 궁금합니다."],
         "B4": [f"{pn} what is this part 설명", f"{pn} 용도 and 특징"], "B5": [f"{pn}뭐하는거야", f"{pn.lower()} 어디에 쓰는건지"]}
    return rng.choice(f[b]), pn


def a5(b, topic, rng):
    doc = rng.choice(["내가 올린 데이터시트", "업로드한 PDF 문서", "제가 올린 자료"])
    f = {"B1": [f"{doc} {topic}"], "B2": [f"{doc}에서 {topic} 찾아줘", f"{doc} {topic} 어디 있는지 알려줘"],
         "B3": [f"{doc} 안에서 {topic}이(가) 어느 쪽에 나오는지 알려 주실 수 있나요?"], "B4": [f"{doc} {topic} page 알려줘", f"uploaded datasheet 의 {topic} 위치"],
         "B5": [f"{doc.replace(' ', '')}{topic}찾아줘", f"{doc.replace(' ', '')} {topic.replace(' ', '')}"]}
    return rng.choice(f[b])


def squeeze(stem, rng):
    """띄어쓰기 변형: 공백을 절반쯤만 없앤다."""
    out = ""
    for i, w in enumerate(stem.split(" ")):
        out += w if i == 0 else (w if rng.random() < 0.5 else " " + w)
    return out


def a6(b, stem, rng):
    f = {"B1": [stem], "B2": [f"{stem} 알려줘", f"{stem} 추천해줘"], "B3": [f"{stem}에 대해 자세히 설명해 주실 수 있나요?", f"{stem}, 어떻게 하면 좋을까요?"],
         "B4": [f"{stem} best tips", f"{stem} 정리 please"], "B5": [squeeze(stem, rng), squeeze(stem, rng) + "알려줘"]}
    return rng.choice(f[b])


SLOTS_NORMAL = [("A1", 0), ("A1", 2), ("A2", 1), ("A2", 3), ("A3", 0), ("A3", 2), ("A4", 0)]
SLOTS_B1 = [("A1", 0), ("A1", 1), ("A1", 2), ("A1", 0), ("A2", 1), ("A2", 3), ("A3", 0), ("A3", 2), ("A4", 0), ("A4", 0)]


def build():
    ps, es = sealed_sets()
    rows = []
    # 부품 묶음 D×B
    for d in D:
        for b in B:
            bundle = f"{d}|{b}"
            split = "sealed" if bundle in ps else "practice"
            slots = SLOTS_B1 if b == "B1" else SLOTS_NORMAL
            used = set()
            for si, (intent, clevel) in enumerate(slots):
                for attempt in range(60):
                    rng = rng_for(bundle, si, attempt)
                    it = rng.choice(L.D_ITEMS[d])
                    lv = 0 if it.get("nocond") else clevel
                    while True:
                        c, nc = cond_text(rng, lv, b == "B1", d) if lv else ("", 0)
                        pn = None
                        if intent == "A1":
                            q = a1(b, it, c, rng)
                        elif intent == "A2":
                            q, pn = a2(b, it, c, rng)
                        elif intent == "A3":
                            d2 = rng.choice([x for x in D if x != d])
                            it2 = rng.choice(L.D_ITEMS[d2])
                            q = a3(b, it, it2, c, rng)
                        else:
                            q, pn = a4(b, it, c, rng)
                        if b != "B1" or nwords(q) <= 4:
                            break
                        if lv > 0:
                            lv -= 1  # B1 은 ≤4 낱말 유지: 조건을 줄여 다시
                        else:
                            q = None
                            break
                    if q and q not in used:
                        used.add(q)
                        break
                else:
                    raise RuntimeError(f"질문을 만들지 못함: {bundle} 슬롯 {si}")
                libs = list(it["libs"])
                kind = "not_parts" if intent == "A4" else "parts"  # 설명 질문은 부품 경로가 아님(프로젝트 결정: 세트 4 '뭐 하는 부품이야' 오처리 사례)
                rec = {"id": f"s1-{d}-{b}-{si:02d}", "kind": kind, "question": q, "intent": intent, "frame": b, "domain": d, "cond": nc if lv else 0, "bundle": bundle,
                       "split": split, "gold_libs": libs}
                if intent == "A3":
                    rec["gold_libs_pair"] = [libs, list(it2["libs"])]
                    rec["gold_libs"] = sorted(set(libs) | set(it2["libs"]))
                    rec["domain2"] = d2
                rec["lib_leak"] = lib_leak(q, rec["gold_libs"])
                if pn:
                    rec["pn"] = pn
                    rec["pn_in_catalog"] = pn_in_catalog(pn)
                rows.append(rec)
    # A5 문서 질문 (B 묶음, 연습만)
    for b in B:
        rng0 = rng_for("A5", b)
        topics = L.A5_TOPICS[:]
        rng0.shuffle(topics)
        for i in range(7):
            q = a5(b, topics[i], rng_for("A5q", b, i))
            rows.append({"id": f"s1-A5-{b}-{i:02d}", "kind": "not_parts", "question": q, "intent": "A5", "frame": b, "cond": 0, "bundle": f"A5|{b}", "split": "practice"})
    # A6: E×B 묶음
    e4 = [(p, a) for p in L.E4_PRODUCTS for a in L.E4_ASPECTS]
    e4.sort(key=lambda x: hashlib.sha256((x[0] + x[1] + SEED).encode()).hexdigest())
    e4 = e4[:90]
    for e in EH:
        for bi, b in enumerate(B):
            bundle = f"{e}|{b}"
            split = "sealed" if bundle in es else "practice"
            if e == "E4":
                stems = [f"{p} {a}" for p, a in e4[bi * 18:(bi + 1) * 18]]
            else:
                stems = L.E_STEMS[e][bi * 5:(bi + 1) * 5]
            for i, stem in enumerate(stems):
                q = a6(b, stem, rng_for(bundle, i))
                rows.append({"id": f"s1-{e}-{b}-{i:02d}", "kind": "not_parts", "question": q, "intent": "A6", "frame": b, "E": e, "cond": 0, "bundle": bundle, "split": split})
    return rows


def main():
    rows = build()
    OUT.mkdir(parents=True, exist_ok=True)
    qs = [r["question"] for r in rows]
    dup = len(qs) - len(set(qs))
    for split in ("practice", "sealed"):
        lst = [r for r in rows if r["split"] == split]
        p = OUT / f"questions-{split}.jsonl"
        p.write_text("\n".join(json.dumps(r, ensure_ascii=False, sort_keys=True) for r in lst) + "\n", encoding="utf-8")
        print(split, len(lst), "sha256", hashlib.sha256(p.read_bytes()).hexdigest())
    sealed = [r for r in rows if r["split"] == "sealed"]
    shuf = sorted(sealed, key=lambda r: hashlib.sha256((r["id"] + "label-order").encode()).hexdigest())
    lp = OUT / "label-input-sealed.jsonl"
    lp.write_text("\n".join(json.dumps({"id": f"L{i:03d}", "question": r["question"]}, ensure_ascii=False) for i, r in enumerate(shuf)) + "\n", encoding="utf-8")
    (OUT / "label-key-sealed.json").write_text(json.dumps({f"L{i:03d}": r["id"] for i, r in enumerate(shuf)}), encoding="utf-8")
    print("label-input", len(shuf), "sha256", hashlib.sha256(lp.read_bytes()).hexdigest(), "| 중복 질문", dup)
    # 칸 규모(봉인)
    sl = sealed
    cnt = lambda f: sum(1 for r in sl if f(r))  # noqa: E731
    print("봉인 칸 규모: A2", cnt(lambda r: r["intent"] == "A2"), "A3", cnt(lambda r: r["intent"] == "A3"), "B1(부품)", cnt(lambda r: r["frame"] == "B1" and r["kind"] == "parts"),
          "C2·C3", cnt(lambda r: r.get("cond", 0) >= 2), "A6×E4", cnt(lambda r: r.get("E") == "E4"), "A5", cnt(lambda r: r["intent"] == "A5"), "부품 질문", cnt(lambda r: r["kind"] == "parts"), "비부품", cnt(lambda r: r["kind"] == "not_parts"))
    print("순환 위험(질문에 라이브러리 이름 낱말) 봉인:", cnt(lambda r: r.get("lib_leak")), "/ 연습:", sum(1 for r in rows if r["split"] == "practice" and r.get("lib_leak")))
    print("B1 4낱말 초과:", sum(1 for r in rows if r["frame"] == "B1" and r["kind"] == "parts" and nwords(r["question"]) > 4))


if __name__ == "__main__":
    main()
