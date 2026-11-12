"""채팅 모델 제공자 선택: 로컬(LM Studio) · OpenAI(호환) · Anthropic.

- 설정은 settings.py(.env)에서만 읽는다. API 키는 응답·로그·브라우저로 내보내지 않는다.
- 키와 모델 이름을 모두 넣은 제공자만 "사용 가능(ready)"으로 표시한다.
- 업로드 문서 내용(RAG 근거)을 외부 API로 보내는 것은 ALLOW_EXTERNAL_RAG=true 일 때만 허용한다.
"""
from __future__ import annotations

import importlib.util
from dataclasses import dataclass

import settings

LABELS = {"local": "로컬 (LM Studio)", "openai": "OpenAI", "anthropic": "Anthropic"}


@dataclass(frozen=True)
class Provider:
    id: str
    label: str
    model: str
    ready: bool
    external: bool
    reason: str = ""

    def public(self) -> dict:
        """화면에 보여 줄 정보 (키 없음)."""
        return {"id": self.id, "label": self.label, "model": self.model,
                "ready": self.ready, "external": self.external, "reason": self.reason}


def _provider(pid: str, cfg=settings) -> Provider:
    label = LABELS.get(pid, pid)
    if pid == "local":
        return Provider("local", label, cfg.CHAT_MODEL, True, False)
    if pid == "openai":
        if not (cfg.OPENAI_API_KEY and cfg.OPENAI_MODEL):
            return Provider(pid, label, cfg.OPENAI_MODEL, False, True, ".env에 OPENAI_API_KEY와 OPENAI_MODEL 필요")
        return Provider(pid, label, cfg.OPENAI_MODEL, True, True)
    if pid == "anthropic":
        if not (cfg.ANTHROPIC_API_KEY and cfg.ANTHROPIC_MODEL):
            return Provider(pid, label, cfg.ANTHROPIC_MODEL, False, True,
                            ".env에 ANTHROPIC_API_KEY와 ANTHROPIC_MODEL 필요")
        if importlib.util.find_spec("langchain_anthropic") is None:
            return Provider(pid, label, cfg.ANTHROPIC_MODEL, False, True,
                            "추가 설치 필요: .venv/bin/python -m pip install langchain-anthropic")
        return Provider(pid, label, cfg.ANTHROPIC_MODEL, True, True)
    return Provider(pid, label, "", False, True, "알 수 없는 제공자")


def providers(cfg=settings) -> list[Provider]:
    """설정된 제공자 목록 (LLM_PROVIDERS 순서)."""
    ids = cfg.LLM_PROVIDERS or ["local"]
    return [_provider(pid, cfg) for pid in ids]


def resolve(provider_id: str | None, mode: str, cfg=settings) -> Provider:
    """요청에 쓸 제공자를 고르고, 쓸 수 없으면 사용자에게 보여 줄 이유와 함께 ValueError."""
    pid = provider_id or cfg.DEFAULT_PROVIDER or "local"
    found = {p.id: p for p in providers(cfg)}
    if pid not in found:
        raise ValueError(f"설정에 없는 모델 제공자입니다: {pid}")
    p = found[pid]
    if not p.ready:
        raise ValueError(f"{p.label}을(를) 사용할 수 없습니다: {p.reason}")
    if p.external and mode == "rag" and not cfg.ALLOW_EXTERNAL_RAG:
        raise ValueError(f"문서 검색(RAG) 내용은 외부 API({p.label})로 보내지 않도록 설정되어 있습니다. "
                         "일반 채팅을 쓰거나 .env의 ALLOW_EXTERNAL_RAG를 확인하세요.")
    return p


def make_chat(p: Provider, cfg=settings, temperature: float = 0, timeout: int = 180):
    """LangChain 채팅 모델 객체 생성. 세 제공자 모두 .invoke(messages) 로 같은 방식으로 호출된다."""
    if p.id == "local":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(model=p.model, base_url=cfg.LM_STUDIO_URL, api_key="lm-studio",
                          temperature=temperature, timeout=timeout, use_responses_api=False)
    if p.id == "openai":
        from langchain_openai import ChatOpenAI
        kwargs = {"model": p.model, "api_key": cfg.OPENAI_API_KEY,
                  "temperature": temperature, "timeout": timeout}
        if cfg.OPENAI_BASE_URL:
            kwargs["base_url"] = cfg.OPENAI_BASE_URL
        return ChatOpenAI(**kwargs)
    if p.id == "anthropic":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(model=p.model, api_key=cfg.ANTHROPIC_API_KEY,
                             temperature=temperature, timeout=timeout, max_tokens=4096)
    raise ValueError(f"알 수 없는 제공자: {p.id}")
