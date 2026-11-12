#!/usr/bin/env python3
"""평가 질문 검토 도구 — 질문·정답·근거 쪽의 본문 발췌를 한 화면에 모아 사람이 확인하게 한다.

평가 질문(data/eval/questions.jsonl)은 초안일 수 있다. 정답과 근거 쪽이 틀리면 채점 자체가 틀리므로,
사람이 한 번 확인한 뒤 status 를 approved 로 바꾼다.

사용:
  .venv/bin/python scripts/eval-review.py sheet              # data/eval/review.html 생성 (내 PC 전용)
  .venv/bin/python scripts/eval-review.py approve q01 q02    # 확인한 문항을 approved 로
  .venv/bin/python scripts/eval-review.py approve --all      # 모두 approved 로
  .venv/bin/python scripts/eval-review.py draft q07          # 다시 초안으로

검토 표에는 내 문서의 본문이 들어가므로 data/ 아래에만 만든다(GitHub에 올라가지 않음).
approve·draft 는 질문 파일의 status 값만 바꾸고, 바꾸기 전 내용을 questions.jsonl.bak 에 남긴다.
색인이나 문서는 건드리지 않는다.
"""
from __future__ import annotations

import argparse
import html
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

QUESTIONS = ROOT / "data" / "eval" / "questions.jsonl"
SHEET = ROOT / "data" / "eval" / "review.html"
EXCERPT_CHARS = 420


def read_lines(path):
    """(원문 줄, 질문 dict 또는 None) 목록. 주석과 빈 줄은 그대로 보존한다."""
    rows = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        item = None if not stripped or stripped.startswith("#") else json.loads(stripped)
        rows.append((line, item))
    return rows


def set_status(path, ids, status, everything=False):
    """지정한 문항의 status 를 바꾸고 바뀐 id 목록을 돌려준다. 없는 id 가 있으면 아무것도 바꾸지 않는다."""
    rows = read_lines(path)
    known = {item["id"] for _, item in rows if item}
    targets = known if everything else set(ids)
    missing = sorted(targets - known)
    if missing:
        raise ValueError("질문 파일에 없는 id: " + ", ".join(missing))
    changed, out = [], []
    for line, item in rows:
        if item and item["id"] in targets and item.get("status", "draft") != status:
            item["status"] = status
            changed.append(item["id"])
            line = json.dumps(item, ensure_ascii=False)
        out.append(line)
    if changed:
        shutil.copy2(path, str(path) + ".bak")
        Path(path).write_text("\n".join(out) + "\n", encoding="utf-8")
    return changed


def evidence(item, documents, sections_of):
    """질문의 근거 쪽마다 (쪽, 발췌, 핵심어 포함 여부). 문서를 찾지 못하면 (None, 이유, False) 하나."""
    from document_pipeline import make_snippet
    matches = [d for d in documents if d["document_id"].startswith(item["document_id"])]
    if len(matches) != 1:
        return None, [(None, f"문서를 찾지 못했습니다 (일치 {len(matches)}개)", False)]
    doc = matches[0]
    try:
        sections = sections_of(doc)
    except Exception as exc:  # 원본이 없거나 추출 실패
        return doc, [(None, f"원본을 읽지 못했습니다: {exc}", False)]
    keywords = item.get("keywords") or []
    rows = []
    for page in item["pages"]:
        text = "\n".join(s["text"] for s in sections if s.get("page") == page)
        if not text:
            rows.append((page, "이 쪽에서 추출된 본문이 없습니다.", False))
            continue
        flat = "".join(text.split()).lower()
        has = any("".join(k.split()).lower() in flat for k in keywords)
        rows.append((page, make_snippet(text, keywords, size=EXCERPT_CHARS), has))
    return doc, rows


def build_sheet(items, documents, sections_of):
    esc = html.escape
    body = []
    for item in items:
        doc, rows = evidence(item, documents, sections_of)
        name = esc(doc.get("filename") or doc["document_id"][:6]) if doc else esc(item["document_id"])
        status = item.get("status", "draft")
        pages = "".join(
            f'<div class="page"><b>{"p." + str(page) if page else "확인 불가"}</b> '
            f'<span class="{"ok" if has else "warn"}">{"핵심어 있음" if has else "핵심어 없음 — 확인 필요"}</span>'
            f'<p>{esc(text)}</p></div>' for page, text, has in rows)
        body.append(
            f'<section class="{esc(status)}"><h2>{esc(item["id"])} <small>{"검토 완료" if status == "approved" else "초안"}</small></h2>'
            f'<dl><dt>질문</dt><dd>{esc(item["question"])}</dd>'
            f'<dt>정답으로 적은 내용</dt><dd>{esc(item.get("answer", ""))}</dd>'
            f'<dt>문서</dt><dd>{name}</dd>'
            f'<dt>핵심어</dt><dd>{esc(", ".join(item.get("keywords") or []))}</dd></dl>'
            f'<h3>근거로 적은 쪽의 본문 발췌</h3>{pages}</section>')
    approved = sum(1 for i in items if i.get("status") == "approved")
    return f'''<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex"><title>평가 질문 검토</title>
<style>
body{{margin:0;background:#f1f5f9;color:#0f172a;font-family:system-ui,"Noto Sans KR",sans-serif;line-height:1.65}}
main{{max-width:900px;margin:auto;padding:24px 16px 80px}}
section{{background:#fff;border:1px solid #cbd5e1;border-left:6px solid #f59e0b;border-radius:10px;padding:16px 18px;margin:16px 0}}
section.approved{{border-left-color:#16a34a}}h1{{font-size:22px}}h2{{font-size:18px;margin:0 0 8px}}h3{{font-size:14px;margin:14px 0 6px;color:#475569}}
small{{font-weight:500;color:#64748b}}dl{{display:grid;grid-template-columns:9em 1fr;gap:4px 12px;margin:0}}dt{{color:#475569}}dd{{margin:0}}
.page{{background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:8px 12px;margin:6px 0}}.page p{{margin:6px 0 0;white-space:pre-wrap;overflow-wrap:anywhere}}
.ok{{color:#15803d}}.warn{{color:#b45309;font-weight:600}}code{{background:#e2e8f0;padding:1px 5px;border-radius:4px}}
</style></head><body><main>
<h1>평가 질문 검토 ({len(items)}문항, 검토 완료 {approved})</h1>
<p>문항마다 <b>질문 · 정답 · 근거 쪽</b>이 맞는지 확인합니다. 맞는 문항은 터미널에서
<code>.venv/bin/python scripts/eval-review.py approve q01 q02</code> 처럼 표시합니다.
틀린 문항은 <code>data/eval/questions.jsonl</code>의 해당 줄을 고친 뒤 이 표를 다시 만듭니다.
이 파일에는 내 문서의 본문이 들어 있으므로 다른 곳에 올리지 않습니다.</p>
{"".join(body)}
</main></body></html>
'''


def main():
    parser = argparse.ArgumentParser(description="평가 질문 검토 도구")
    parser.add_argument("--questions", default=str(QUESTIONS))
    sub = parser.add_subparsers(dest="command", required=True)
    sheet = sub.add_parser("sheet", help="검토용 표 만들기")
    sheet.add_argument("--out", default=str(SHEET))
    for name in ("approve", "draft"):
        cmd = sub.add_parser(name, help="문항 상태 바꾸기")
        cmd.add_argument("ids", nargs="*")
        cmd.add_argument("--all", action="store_true")
    args = parser.parse_args()

    if args.command == "sheet":
        from document_pipeline import UPLOAD_DIR, extract_sections, get_document, list_documents
        cache = {}

        def sections_of(doc):
            key = doc["document_id"]
            if key not in cache:
                meta = get_document(key)
                cache[key] = extract_sections(UPLOAD_DIR / f'{key}{meta["format"]}')
            return cache[key]

        items = [item for _, item in read_lines(args.questions) if item]
        Path(args.out).write_text(build_sheet(items, list_documents(), sections_of), encoding="utf-8")
        print(f"검토용 표를 만들었습니다: {args.out} ({len(items)}문항)")
        print("브라우저로 열어 확인하세요. 내 문서의 본문이 들어 있으므로 다른 곳에 올리지 않습니다.")
        return 0

    if not args.all and not args.ids:
        print("문항 id 를 적거나 --all 을 쓰세요. 예: approve q01 q02")
        return 2
    status = "approved" if args.command == "approve" else "draft"
    try:
        changed = set_status(args.questions, args.ids, status, everything=args.all)
    except ValueError as exc:
        print("바꾸지 않았습니다:", exc)
        return 2
    print(f"{status} 로 바꾼 문항 {len(changed)}개: {', '.join(changed) or '없음(이미 그 상태)'}")
    if changed:
        print(f"바꾸기 전 내용: {args.questions}.bak")
    return 0


if __name__ == "__main__":
    sys.exit(main())
