#!/usr/bin/env python3
"""과적합 적대 감사(읽기 전용): 판정에 쓴 질문 세트가 규칙 낱말에 '새어 들어갔는지'와, 개발 세트 대비 봉인 세트의 효과 차이를 본다.

leak : 세트 S 를 만든 시각(파일 수정 시각) 뒤에 코드·사전에 새로 들어간 낱말 중 S 의 질문에 나오는 것을 찾는다.
       규칙 낱말이 세트를 본 뒤에 추가됐고 그 세트 질문에 있다면 맞춰 넣은 것일 수 있다(후보이지 판결이 아니다).
       너무 흔한 낱말(전체 질문의 일정 비율 이상에 나옴)은 뺀다. 출력은 낱말과 커밋 시각만 — 질문 원문은 쓰지 않는다.
gap  : static_data/verification/gap_table.json 의 (개발 세트 효과, 봉인 세트 효과)를 질문 100개당 효과로 맞춰 비율을 낸다. 비율 > 2 면 의심.
사용: .venv/bin/python scripts/audit-overfit.py leak|gap|all [--max-df 0.2]
출력: 화면 + data/eval/audit/overfit-<날짜>.md (이 PC 전용)
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EVAL = ROOT / "data" / "eval"
GAP = ROOT / "static_data" / "verification" / "gap_table.json"
RULE_FILES = ["parts_graph.py", "parts_taxonomy.py", "part_conditions.py", "ontology_graph.py", "query_translate.py", "bridge_terms.py",
              "static_data/parts_taxonomy.json", "static_data/ontology_ko_en_seed.json", "routing.py", "kicad_parts.py"]
TOKEN = re.compile(r"[가-힣]{2,}|[a-z][a-z0-9+\-]{2,}")


def tokens(text: str) -> set[str]:
    return set(TOKEN.findall(text.lower()))


def load_sets() -> dict[str, dict]:
    """질문 세트 파일 → {'questions': [...], 'mtime': 시각, 'owner': ...}. 71 로 시작하는 이름은 동료가 쓴 세트."""
    out = {}
    for f in sorted(EVAL.glob("parts-ko-questions*.jsonl")):
        qs = []
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.strip() and not line.lstrip().startswith("#"):
                try:
                    qs.append(json.loads(line)["question"])
                except (ValueError, KeyError):
                    pass
        owner = "71(동료)" if re.search(r"-71", f.name) else "jung-29"
        out[f.name] = {"questions": qs, "mtime": f.stat().st_mtime, "owner": owner}
    return out


def added_words(since_ts: float) -> list[tuple[str, float, str]]:
    """since_ts 뒤 커밋에서 규칙 파일에 '추가된 줄'의 낱말 → [(낱말, 커밋 시각, 커밋 해시)]."""
    cmd = ["git", "-C", str(ROOT), "log", f"--since=@{int(since_ts)}", "-p", "--format=@@COMMIT %H %ct", "--no-color", "--"] + RULE_FILES
    res = subprocess.run(cmd, capture_output=True, text=True, errors="replace")
    out, cur = [], None
    for line in res.stdout.splitlines():
        if line.startswith("@@COMMIT "):  # diff 조각 머리줄("@@ -1,3 +1,4 @@")과 구분
            h, ct = line[len("@@COMMIT "):].split()
            cur = (h[:7], float(ct))
        elif cur and line.startswith("+") and not line.startswith("+++"):
            for w in tokens(line[1:]):
                out.append((w, cur[1], cur[0]))
    return out


def leak(max_df: float) -> list[str]:
    sets = load_sets()
    allq = [q for s in sets.values() for q in s["questions"]]
    df = Counter()
    for q in allq:
        for t in tokens(q):
            df[t] += 1
    common = {t for t, n in df.items() if n / max(len(allq), 1) >= max_df}
    lines = [f"## 낱말 새어 들어감 후보 (흔한 낱말 {len(common)}개 제외, 기준 df≥{max_df:.0%})", ""]
    earliest = min(s["mtime"] for s in sets.values())
    added = added_words(earliest)
    by_word = defaultdict(list)
    for w, ts, h in added:
        by_word[w].append((ts, h))
    for name, s in sets.items():
        qtok = set().union(*[tokens(q) for q in s["questions"]]) if s["questions"] else set()
        hits = []
        for w, lst in by_word.items():
            if w in qtok and w not in common:
                later = [x for x in lst if x[0] > s["mtime"]]
                if later:
                    hits.append((w, min(later)))
        lines.append(f"### {name} ({s['owner']}, 질문 {len(s['questions'])}개, 만든 시각 {datetime.fromtimestamp(s['mtime']):%m-%d %H:%M})")
        if not hits:
            lines += ["- 만든 뒤 추가된 규칙 낱말 중 이 세트 질문에 나오는 것: 없음", ""]
            continue
        hits.sort(key=lambda x: x[1][0])
        lines.append(f"- 만든 뒤 규칙에 추가된 낱말 중 이 세트 질문에도 나오는 것 {len(hits)}개(후보): " +
                     ", ".join(f"{w}({h[1]})" for w, h in hits[:40]) + (" …" if len(hits) > 40 else ""))
        lines.append("")
    return lines


def gap() -> list[str]:
    if not GAP.exists():
        return [f"## 개발·봉인 효과 차이", "", f"- {GAP.name} 이 아직 없어 건너뜀(판정 결과를 기록하는 표, 아직 작성 전)"]
    data = json.loads(GAP.read_text(encoding="utf-8"))
    lines = ["## 개발 세트 효과 대 봉인 세트 효과(질문 100개당)", "",
             "| 변경 | 개발 효과/100 | 봉인 효과/100 | 비율 | 판정 | 출처 |", "|---|---|---|---|---|---|"]
    ratios = []
    for r in data["rows"]:
        dev = r["dev_gain"] / r["dev_n"] * 100
        sealed = r["sealed_gain"] / r["sealed_n"] * 100
        ratio = (dev / sealed) if sealed > 0 else (float("inf") if dev > 0 else 0.0)
        flag = "의심(>2배)" if ratio > 2 else ("봉인이 더 나쁨" if sealed < 0 else "정상 범위")
        ratios.append((r["change"], ratio))
        lines.append(f"| {r['change']} | {dev:+.1f} | {sealed:+.1f} | {'∞' if ratio == float('inf') else f'{ratio:.1f}'} | {flag} | {r['source']} |")
    finite = [x for _, x in ratios if x != float("inf")]
    lines += ["", f"- 개발 효과가 있었는데 봉인 효과가 0 이하인 변경: {sum(1 for _, x in ratios if x == float('inf'))}개 / 전체 {len(ratios)}개",
              f"- 비율이 유한한 변경의 중앙값: {sorted(finite)[len(finite)//2]:.1f}" if finite else "",
              "- 해석: 개발 세트가 작고 규칙을 만든 사람이 쓴 것이면 비율이 커진다. 앞으로 개발 효과가 봉인 효과의 2배를 넘는 변경은 '개발 세트에 맞춘 것'으로 보고 채택 전에 새 봉인 세트로 다시 본다.", ""]
    return lines


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("what", choices=["leak", "gap", "all"])
    ap.add_argument("--max-df", type=float, default=0.2)
    args = ap.parse_args()
    out = [f"# 과적합 적대 감사 ({date.today()})", ""]
    if args.what in ("gap", "all"):
        out += gap()
    if args.what in ("leak", "all"):
        out += leak(args.max_df)
    text = "\n".join(out)
    d = EVAL / "audit"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"overfit-{date.today()}.md").write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
