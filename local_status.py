"""로컬 서비스 상태 요약과 공개 시작 페이지용 CORS 규칙 (읽기 전용).

공개 GitHub Pages(https://yuul-jung.github.io/langchain-lab/)의 '상태 확인' 버튼이
브라우저에서 http://127.0.0.1:8000/api/status 를 조회할 수 있게 한다.

- 허용 경로는 /api/status 하나, 허용 메서드는 GET 하나뿐이다.
  채팅·업로드·문서 목록 같은 다른 API는 공개 페이지에서 읽거나 호출할 수 없다.
- 응답에는 모델 ID·상태·버전·조치 명령만 담는다. 문서 내용, 파일명, 비밀번호는 담지 않는다.
"""
from __future__ import annotations

import requests

import settings

STATUS_PATH = "/api/status"
# (변경) settings.py에서 읽음 (.env 의 STATUS_ALLOWED_ORIGINS)
ALLOWED_STATUS_ORIGINS = settings.STATUS_ALLOWED_ORIGINS


def cors_headers(path: str, origin: str | None, method: str,
                 private_network: bool = False) -> dict | None:
    """허용된 출처의 /api/status 요청에만 CORS 헤더를 돌려준다. 그 외는 None."""
    if path != STATUS_PATH or not origin or origin not in ALLOWED_STATUS_ORIGINS:
        return None
    headers = {"Access-Control-Allow-Origin": origin, "Vary": "Origin"}
    if method == "OPTIONS":
        headers["Access-Control-Allow-Methods"] = "GET"
        headers["Access-Control-Max-Age"] = "600"
        # 공개 사이트 → 내 PC(루프백) 요청에 대한 Chrome 사설망 접근 사전 확인 응답
        if private_network:
            headers["Access-Control-Allow-Private-Network"] = "true"
    return headers


def lmstudio_root(lm_url: str) -> str:
    """http://127.0.0.1:1234/v1 → http://127.0.0.1:1234"""
    url = lm_url.rstrip("/")
    return url[:-3] if url.endswith("/v1") else url


def fetch_model_states(lm_url: str, timeout: float = 4) -> list[dict] | None:
    """LM Studio REST(/api/v0/models)에서 모델별 로드 상태를 읽는다. 연결 실패 시 None."""
    try:
        resp = requests.get(lmstudio_root(lm_url) + "/api/v0/models", timeout=timeout)
        resp.raise_for_status()
        rows = resp.json().get("data", [])
    except (requests.RequestException, ValueError):
        return None
    return [
        {"id": m.get("id"), "type": m.get("type"), "state": m.get("state"),
         "context": m.get("loaded_context_length")}
        for m in rows if m.get("id")
    ]


def _find(states, model_id):
    return next((m for m in states if m["id"] == model_id), None)


def memory_blockers(states, chat_model: str) -> list[str]:
    """채팅 모델이 안 올라간 상태에서 메모리를 차지하고 있는 다른 생성/비전 모델."""
    chat = _find(states, chat_model)
    if chat is None or chat["state"] == "loaded":
        return []
    return [m["id"] for m in states
            if m["state"] == "loaded" and m["type"] in ("llm", "vlm") and m["id"] != chat_model]


def chat_failure_hint(states, chat_model: str) -> str:
    """채팅 요청 실패 시 사용자에게 보여줄 원인·조치 한 줄."""
    if states is None:
        return (f"LM Studio 서버({lmstudio_root(settings.LM_STUDIO_URL).split('//')[-1]})에 연결할 수 없습니다. "
                "lms server start 로 시작하세요.")
    if _find(states, chat_model) is None:
        return f"LM Studio에 {chat_model} 모델이 없습니다. 모델 ID를 확인하세요."
    blockers = memory_blockers(states, chat_model)
    if blockers:
        unload = " && ".join(f"lms unload {b}" for b in blockers)
        return (f"{', '.join(blockers)} 모델이 메모리를 차지해 {chat_model}을(를) 올리지 못했을 수 있습니다. "
                f"{unload} && lms load {chat_model}")
    return f"{chat_model} 모델 로드 또는 응답이 실패했습니다. lms load {chat_model} 후 다시 시도하세요."


def build_status(states, *, chat_model: str, embedding_model: str,
                 es_ok: bool | None, es_version: str | None = None) -> dict:
    """구성 요소별 상태(ok/warn/error)와 조치 명령 목록."""
    comps = [{"name": "FastAPI", "level": "ok", "detail": "127.0.0.1:8000 응답"}]
    advice = []

    if states is None:
        comps.append({"name": "LM Studio", "level": "error",
                      "detail": f"{lmstudio_root(settings.LM_STUDIO_URL).split('//')[-1]} 연결 실패"})
        advice.append({"text": "LM Studio 서버를 시작하세요.", "command": "lms server start"})
    else:
        loaded = [m["id"] for m in states if m["state"] == "loaded"]
        comps.append({"name": "LM Studio", "level": "ok",
                      "detail": "로드됨: " + (", ".join(loaded) if loaded else "없음")})
        chat = _find(states, chat_model)
        if chat is None:
            comps.append({"name": "채팅 모델", "level": "error", "detail": f"{chat_model} 없음"})
        elif chat["state"] == "loaded":
            comps.append({"name": "채팅 모델", "level": "ok", "detail": f"{chat_model} 로드됨"})
        else:
            blockers = memory_blockers(states, chat_model)
            comps.append({"name": "채팅 모델", "level": "warn",
                          "detail": f"{chat_model} 미로드 — 첫 질문 때 자동 로드를 시도함"})
            if blockers:
                advice.append({
                    "text": f"{', '.join(blockers)} 이(가) 메모리를 차지하고 있어 채팅 모델 로드가 실패할 수 있습니다. "
                            "비전 모델 작업(제3장)이 끝났으면 내리고 채팅 모델을 미리 올리세요.",
                    "command": " && ".join(f"lms unload {b}" for b in blockers) + f" && lms load {chat_model}",
                })
            else:
                advice.append({"text": "채팅 모델을 미리 올려 두면 첫 응답이 빨라집니다.",
                               "command": f"lms load {chat_model}"})
        emb = _find(states, embedding_model)
        if emb is None:
            comps.append({"name": "임베딩 모델", "level": "error", "detail": f"{embedding_model} 없음"})
        else:
            comps.append({"name": "임베딩 모델", "level": "ok",
                          "detail": f"{embedding_model} " + ("로드됨" if emb["state"] == "loaded"
                                                              else "필요할 때 자동 로드")})

    if es_ok:
        comps.append({"name": "Elasticsearch", "level": "ok", "detail": f"연결됨 {es_version or ''}".strip()})
    else:
        comps.append({"name": "Elasticsearch", "level": "error", "detail": "연결 실패"})
        advice.append({"text": "Elasticsearch를 시작하세요 (관리자 권한).",
                       "command": "sudo systemctl start elasticsearch"})

    worst = "ok"
    for c in comps:
        if c["level"] == "error":
            worst = "error"
        elif c["level"] == "warn" and worst == "ok":
            worst = "warn"
    return {"overall": worst, "components": comps, "advice": advice}
