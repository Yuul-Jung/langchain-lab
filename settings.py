"""LangChain Lab 설정 한곳 모음.

값을 찾는 순서: 프로젝트 .env → 프로세스 환경변수 → 아래 기본값.
.env를 먼저 보는 이유는 rag_search.es_settings()와 같다: 데스크톱·systemd 세션에
남아 있는 예전 환경변수가 방금 저장한 .env 값을 조용히 덮어쓰지 않게 하기 위해서다.

AI PC로 옮길 때는 코드를 고치지 않고 .env의 값만 바꾼다.
기본값은 2026-11-12까지 코드에 고정되어 있던 값과 같다(동작 변화 없음).
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parent
ENV_FILE = ROOT / ".env"


def _load():
    return dotenv_values(ENV_FILE) if ENV_FILE.is_file() else {}


_VALUES = _load()


def get(name: str, default: str = "") -> str:
    """설정 하나 읽기 (.env → 환경변수 → 기본값)."""
    return _VALUES.get(name) or os.environ.get(name) or default


def get_int(name: str, default: int) -> int:
    try:
        return int(get(name, str(default)))
    except ValueError:
        return default


def get_list(name: str, default: str = "") -> list[str]:
    return [v.strip() for v in get(name, default).split(",") if v.strip()]


# ---- LM Studio (로컬 모델 서버)
LM_STUDIO_URL = get("LM_STUDIO_URL", "http://127.0.0.1:1234/v1")
CHAT_MODEL = get("CHAT_MODEL", "deepseek-r1-distill-qwen-14b")
EMBEDDING_MODEL = get("EMBEDDING_MODEL", "text-embedding-qwen3-embedding-4b")
# 인덱스 매핑과 반드시 같아야 한다. 바꾸면 기존 색인을 모두 다시 만들어야 한다.
EMBEDDING_DIMS = get_int("EMBEDDING_DIMS", 2560)

# ---- Elasticsearch 인덱스
ES_RAG_INDEX = get("ES_RAG_INDEX", "langchain_embedding_lab")
ES_DOCUMENT_INDEX = get("ES_DOCUMENT_INDEX", "langchain_documents_v1")
# (추가) 검색 결과 컷오프: 1위 점수에서 이 폭 안의 결과만 보여 준다 (0 이면 끔). 점수 범위는 0~1.
try:
    SEARCH_SCORE_MARGIN = float(get("SEARCH_SCORE_MARGIN", "0.05"))
except ValueError:
    SEARCH_SCORE_MARGIN = 0.05
# (추가) 채팅 RAG 검색 대상: documents(업로드 문서, 기본) · lab(제1장 실습 문장) · both
CHAT_RAG_SOURCE = get("CHAT_RAG_SOURCE", "documents").lower()

# ---- 공개 시작 페이지가 /api/status 를 읽을 수 있는 출처
STATUS_ALLOWED_ORIGINS = frozenset(get_list("STATUS_ALLOWED_ORIGINS", "https://yuul-jung.github.io"))

# ---- 채팅 모델 제공자 (llm_providers.py)
# 사용할 제공자 목록. local 은 LM Studio, openai·anthropic 은 키를 넣어야 켜진다.
LLM_PROVIDERS = get_list("LLM_PROVIDERS", "local,openai,anthropic")
DEFAULT_PROVIDER = get("DEFAULT_PROVIDER", "local")
OPENAI_API_KEY = get("OPENAI_API_KEY")
OPENAI_MODEL = get("OPENAI_MODEL")
OPENAI_BASE_URL = get("OPENAI_BASE_URL")          # 비우면 OpenAI 기본 주소, 호환 서비스면 그 주소
ANTHROPIC_API_KEY = get("ANTHROPIC_API_KEY")
ANTHROPIC_MODEL = get("ANTHROPIC_MODEL")
# 업로드 문서 내용(RAG 근거)을 외부 API로 보내도 되는지. 기본은 보내지 않음.
ALLOW_EXTERNAL_RAG = get("ALLOW_EXTERNAL_RAG", "false").lower() in ("1", "true", "yes")


def describe() -> dict:
    """비밀값을 빼고 현재 설정을 보여 준다 (진단용)."""
    return {
        "lm_studio_url": LM_STUDIO_URL, "chat_model": CHAT_MODEL,
        "embedding_model": EMBEDDING_MODEL, "embedding_dims": EMBEDDING_DIMS,
        "es_rag_index": ES_RAG_INDEX, "es_document_index": ES_DOCUMENT_INDEX,
        "chat_rag_source": CHAT_RAG_SOURCE, "search_score_margin": SEARCH_SCORE_MARGIN,
        "llm_providers": LLM_PROVIDERS, "default_provider": DEFAULT_PROVIDER,
        "openai_configured": bool(OPENAI_API_KEY and OPENAI_MODEL),
        "anthropic_configured": bool(ANTHROPIC_API_KEY and ANTHROPIC_MODEL),
        "allow_external_rag": ALLOW_EXTERNAL_RAG,
    }
