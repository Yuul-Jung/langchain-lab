"""제3장 — 페이지 이미지 VLM 분석과 OCR 대조 (표준 라이브러리만 사용).

LM Studio의 OpenAI 호환 API(/v1/chat/completions)로 Qwen3-VL 같은 비전 모델에
페이지 이미지를 보내고, 그 요약에 나온 영문 식별자를 Tesseract OCR 원문과 대조한다.

검증된 사실 (LM Studio + qwen3-vl-4b, 2026-11):
- 이미지는 반드시 base64 data URI(data:image/png;base64,...)로 보낸다.
  file:// 경로는 "'url' field must be a base64 encoded image."로 거부된다.
- A4 300dpi 페이지(2481x3508) 한 장이 약 4,000 토큰을 차지한다.
  기본 컨텍스트 4096으로 로드하면 exceed_context_size_error(HTTP 400)가 난다.
"""
from __future__ import annotations

import base64
import json
import re
import urllib.error
import urllib.request
from difflib import SequenceMatcher
from pathlib import Path

DEFAULT_BASE_URL = "http://127.0.0.1:1234/v1"
DEFAULT_MODEL = "qwen3-vl-4b"
DEFAULT_PROMPT = (
    "이 이미지는 PDF 강의자료의 한 페이지입니다. 보이는 내용을 한국어로 정리하세요.\n"
    "1) 페이지 주제\n2) 핵심 항목 목록\n"
    "3) 코드/구조도/처리 흐름이 있으면 그 내용도 설명하세요."
)

# --------------------------------------------------------------------------- VLM


def image_data_uri(path: Path) -> str:
    """PNG/JPEG 파일을 LM Studio가 받는 base64 data URI로 변환한다."""
    suffix = path.suffix.lower()
    mime = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}.get(suffix)
    if mime is None:
        raise ValueError(f"지원하지 않는 이미지 형식: {suffix}")
    return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode("ascii")


def build_payload(image_uri: str, *, model: str = DEFAULT_MODEL,
                  prompt: str = DEFAULT_PROMPT, max_tokens: int = 2048,
                  temperature: float = 0.1) -> dict:
    if not image_uri.startswith("data:image/"):
        # file:// 나 http:// 를 넘기면 LM Studio가 400으로 거부한다.
        raise ValueError("image_uri는 data:image/...;base64, 형식이어야 합니다")
    return {
        "model": model,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": image_uri}},
        ]}],
    }


def explain_http_error(body: str) -> str:
    """LM Studio 400 응답 본문을 사람이 읽을 조치 안내로 바꾼다."""
    text = body or ""
    m = re.search(r"request \((\d+) tokens\) exceeds the available context size \((\d+) tokens\)", text)
    if m or "exceed_context_size" in text:
        need = f"{m.group(1)} 토큰 요청 / 컨텍스트 {m.group(2)}" if m else "컨텍스트 초과"
        return (f"컨텍스트 부족 ({need}). 이미지 1장 ≈ 4,000 토큰 + 답변 max_tokens가 필요합니다. "
                "lms unload <모델> && lms load <모델> --context-length 16384 후 다시 실행하세요.")
    if "must be a base64 encoded image" in text:
        return "이미지는 file:// 경로가 아니라 data:image/png;base64,... 형식으로 보내야 합니다."
    if "Failed to load image" in text:
        return "이미지 바이트를 디코딩하지 못했습니다. 파일이 손상되지 않았는지(PNG/JPEG) 확인하세요."
    if "model" in text.lower() and "not found" in text.lower():
        return "모델 ID가 다릅니다. curl -s http://127.0.0.1:1234/v1/models 로 실제 id를 확인하세요."
    return "응답 본문을 확인하세요."


def call_vlm(payload: dict, *, base_url: str = DEFAULT_BASE_URL, timeout: int = 300) -> dict:
    """성공 시 {'content', 'finish_reason'}; 실패 시 RuntimeError(본문+안내)."""
    req = urllib.request.Request(
        base_url.rstrip("/") + "/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        # 본문을 반드시 읽어야 원인이 보인다. "400 Bad Request"만으로는 진단할 수 없다.
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {body[:400]}\n→ {explain_http_error(body)}") from None
    except urllib.error.URLError as exc:
        raise RuntimeError(f"LM Studio 연결 실패: {exc.reason} → lms server status 확인") from None
    choice = data["choices"][0]
    return {"content": choice["message"]["content"],
            "finish_reason": choice.get("finish_reason")}


# ------------------------------------------------------------------- OCR 대조

TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9]*(?:[-_.][A-Za-z0-9]+)*")


def identifiers(text: str) -> set[str]:
    """클래스명(CamelCase), 하이픈+숫자 이름(gpt-4o-mini), 짧은 대문자 약어(BM25)."""
    out = set()
    for tok in TOKEN.findall(text):
        tok = tok.strip("._-")
        camel = re.search(r"[a-z][A-Z]", tok) and len(tok) >= 6
        joined = re.search(r"[-_.]", tok) and re.search(r"\d", tok)
        upper = tok.isupper() and 2 <= len(tok) <= 6
        if camel or joined or upper:
            out.add(tok)
    return out


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def best_similar(term: str, candidates, threshold: float = 0.8):
    """길이가 거의 같은 후보 중 가장 비슷한 것. 'PgVectorStore'와 'VectorStore'처럼
    한쪽이 다른 쪽을 포함하는 경우는 오타가 아니므로 길이 조건으로 걸러낸다."""
    n = norm(term)
    allow = max(1, round(len(n) * 0.1))
    best, best_r = None, 0.0
    for cand in candidates:
        c = norm(cand)
        if not c or abs(len(c) - len(n)) > allow:
            continue
        r = SequenceMatcher(None, n, c).ratio()
        if r > best_r:
            best, best_r = cand, r
    return (best, best_r) if best_r >= threshold else (None, 0.0)


def check_term(term: str, ocr_text: str) -> tuple[str, str]:
    """('일치'|'유사'|'없음', 상세)."""
    if norm(term) and norm(term) in norm(ocr_text):
        return "일치", term
    cand, ratio = best_similar(term, TOKEN.findall(ocr_text))
    if cand:
        return "유사", f"{cand} ({ratio:.2f})"
    return "없음", ""


def compare_page(vlm_text: str, ocr_texts: dict[str, str]) -> dict:
    """VLM 식별자별 판정과, OCR 공통 식별자 중 VLM이 다루지 않은 것."""
    rows = []
    for term in sorted(identifiers(vlm_text), key=str.lower):
        results = {eng: check_term(term, txt) for eng, txt in ocr_texts.items()}
        ok = any(state in ("일치", "유사") for state, _ in results.values())
        rows.append({"term": term, "results": results, "confirmed": ok})

    engine_sets = [identifiers(t) for t in ocr_texts.values() if t]
    common = set.intersection(*engine_sets) if engine_sets else set()
    vlm_terms = identifiers(vlm_text)
    missed = sorted(
        t for t in common
        if norm(t) not in norm(vlm_text) and best_similar(t, vlm_terms)[0] is None
    )
    return {"rows": rows, "missed": missed}


def render_markdown(pages: dict[int, dict], engines: list[str]) -> str:
    lines = ["# OCR ↔ VLM 식별자 대조 보고서", "",
             "- 일치: OCR 원문에 그대로 있음 / 유사: OCR 오독 가능성 / 없음: VLM 추가 또는 OCR 누락 후보",
             "- RAG·LLM 같은 일반 약어는 VLM이 설명용으로 덧붙인 것일 수 있어 '의심'이 곧 오류는 아님", ""]
    for page, res in pages.items():
        lines += [f"## {page}쪽", "",
                  "| VLM 식별자 | " + " | ".join(engines) + " | 판정 |",
                  "|---|" + "---|" * len(engines) + "---|"]
        for row in res["rows"]:
            cells = []
            for eng in engines:
                state, detail = row["results"].get(eng, ("없음", ""))
                cells.append(f"유사 {detail}" if state == "유사" else state)
            verdict = "확인" if row["confirmed"] else "**의심**"
            lines.append(f"| `{row['term']}` | " + " | ".join(cells) + f" | {verdict} |")
        missed = ", ".join(f"`{t}`" for t in res["missed"]) or "없음"
        lines += ["", f"**VLM이 다루지 않은 OCR 식별자 (모든 엔진 공통):** {missed}", ""]
    return "\n".join(lines)
