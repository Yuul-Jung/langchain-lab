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
# (추가) 접근 제어 (access_control.py). ACCESS_PASSWORD 를 비우면 이 PC 에서만 쓸 수 있다.
ACCESS_PASSWORD = get("ACCESS_PASSWORD")
SESSION_HOURS = get_int("SESSION_HOURS", 12)
# 비우면 서버를 시작할 때마다 새로 만든다 (재시작하면 다시 로그인)
SESSION_SECRET = get("SESSION_SECRET")
# 같은 PC 에 리버스 프록시를 두면 모든 요청이 이 PC 에서 온 것으로 보이므로 true 로 바꾼다
AUTH_REQUIRE_LOOPBACK = get("AUTH_REQUIRE_LOOPBACK", "false").lower() in ("1", "true", "yes")
# HTTPS(리버스 프록시)로만 접속할 때 true: 세션 쿠키를 HTTPS 에서만 보낸다
AUTH_COOKIE_SECURE = get("AUTH_COOKIE_SECURE", "false").lower() in ("1", "true", "yes")
# 이 PC 에서 로그인 없이 쓸 때 허용할 추가 주소 이름 (기본: 127.0.0.1, localhost)
ALLOWED_HOSTS = get_list("ALLOWED_HOSTS", "")

# (추가) 업로드 한도. 슬라이드형 PDF는 쪽마다 절이 하나라 183쪽 문서가 절 150개 한도에 걸렸다(2026-11-12).
# 색인은 청크당 약 0.1초이므로 800청크면 1~2분 걸린다.
UPLOAD_MAX_MB = get_int("UPLOAD_MAX_MB", 30)
UPLOAD_MAX_SECTIONS = get_int("UPLOAD_MAX_SECTIONS", 600)
UPLOAD_MAX_CHUNKS = get_int("UPLOAD_MAX_CHUNKS", 800)
# (추가) 검색 결과 컷오프: 1위 점수에서 이 폭 안의 결과만 보여 준다 (0 이면 끔). 점수 범위는 0~1.
try:
    SEARCH_SCORE_MARGIN = float(get("SEARCH_SCORE_MARGIN", "0.05"))
except ValueError:
    SEARCH_SCORE_MARGIN = 0.05
# (추가) 낱말 포함 재순위 가중치: 질문 낱말이 본문에 들어 있는 비율 × 이 값을 벡터 점수에 더한다 (0 이면 끔)
try:
    SEARCH_TERM_WEIGHT = float(get("SEARCH_TERM_WEIGHT", "0.15"))
except ValueError:
    SEARCH_TERM_WEIGHT = 0.15
# (추가) 채팅 RAG 검색 대상: documents(업로드 문서, 기본) · lab(제1장 실습 문장) · both
CHAT_RAG_SOURCE = get("CHAT_RAG_SOURCE", "documents").lower()
# (추가) 채팅 답변에 한자 1자·가나 등이 섞였을 때 모델에게 한 번 고치게 할지 (기본 켬, false 면 이전처럼 그대로 보냄)
CHAT_LIGHT_LEAK_FIX = get("CHAT_LIGHT_LEAK_FIX", "true").lower() in ("1", "true", "yes")
# 자동 모드가 "올려 둔 문서에 근거가 있다"고 판단하는 기준 (routing.py). 1위 검색 결과의 점수가 문턱 이상이고
# 질문 낱말이 본문에 ROUTE_DOC_MIN_TERMS 개 이상 있어야 한다. 값을 올리면 일반 대화로 더 자주 넘어간다.
try:
    ROUTE_DOC_MIN_SCORE = float(get("ROUTE_DOC_MIN_SCORE", "0.78"))
    ROUTE_DOC_STRONG_SCORE = float(get("ROUTE_DOC_STRONG_SCORE", "0.85"))   # 이 미만이면 "근거가 약함" 표시
    ROUTE_ELLIPSIS_MAX_DROP = float(get("ROUTE_ELLIPSIS_MAX_DROP", "0.02"))   # 지시어 없는 짧은 후속: 직전 질문에 덧붙인 검색 점수가 이만큼 이하로만 떨어지면 이어받음(0이면 끔)
    ROUTE_FOLLOWUP_MAX_CHARS = int(get("ROUTE_FOLLOWUP_MAX_CHARS", "20"))   # 이 글자 수 이하의 짧은 질문은 직전 질문의 처리 방식을 이어받는다(0이면 끔)
    ROUTE_DOC_MIN_TERMS = int(get("ROUTE_DOC_MIN_TERMS", "1"))
except ValueError:
    ROUTE_DOC_MIN_SCORE, ROUTE_DOC_MIN_TERMS, ROUTE_DOC_STRONG_SCORE, ROUTE_FOLLOWUP_MAX_CHARS = 0.78, 1, 0.85, 20
    ROUTE_ELLIPSIS_MAX_DROP = 0.02
# 답에 섞인 한자를 한자 음 표(static_data/hanja_ko.json)로 먼저 고친다(모델 호출 없음). 끄려면 CHAT_HANJA_TABLE=false
CHAT_HANJA_TABLE = get("CHAT_HANJA_TABLE", "true").lower() in ("1", "true", "yes")
# 모델이 못 고쳤어도 한국어가 대부분인 답은 안내 문구로 바꾸지 않고 원래 답을 보여 준다(사용자 결정 2026-11-13).
# 끄려면 CHAT_KEEP_DRAFT_ON_FAIL=false (이전처럼 안내 문구로 바꿈)
CHAT_KEEP_DRAFT_ON_FAIL = get("CHAT_KEEP_DRAFT_ON_FAIL", "true").lower() in ("1", "true", "yes")
# 답이 안내 문구로 바뀔 때 바뀌기 전의 답을 data/diagnostics/fallback.jsonl 에 남긴다(이 PC 전용). 끄려면 CHAT_FALLBACK_LOG=false
CHAT_FALLBACK_LOG = get("CHAT_FALLBACK_LOG", "true").lower() in ("1", "true", "yes")
# 문서 근거로 답할 때, 모델이 [자료 N] 을 빼먹으면 답과 글이 겹치는 근거를 코드로 찾아 '근거:' 줄을 붙인다(모델 호출 없음).
# 평가(22문항, 개발/보류 분리): 정답 쪽을 가리키는 비율 0.47~0.49 → 0.85~0.97. 끄려면 CHAT_AUTO_CITE=false
CHAT_AUTO_CITE = get("CHAT_AUTO_CITE", "true").lower() in ("1", "true", "yes")
# 부품 핀 답변에 LibrePCB 공개 라이브러리(CC0, 커뮤니티 데이터·사람 승인 전)에만 있는 부품을 포함한다. 끄려면 CHAT_PARTS_LIBREPCB=false
CHAT_PARTS_LIBREPCB = get("CHAT_PARTS_LIBREPCB", "true").lower() in ("1", "true", "yes")
# 일반 채팅에서 부품 핀 질문은 KiCad 라이브러리 값으로 바로 답한다(모델을 거치지 않음). 끄려면 CHAT_PARTS_LOOKUP=false
CHAT_PARTS_LOOKUP = get("CHAT_PARTS_LOOKUP", "true").lower() in ("1", "true", "yes")

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
        "search_term_weight": SEARCH_TERM_WEIGHT,
        "chat_light_leak_fix": CHAT_LIGHT_LEAK_FIX, "chat_parts_lookup": CHAT_PARTS_LOOKUP, "chat_parts_librepcb": CHAT_PARTS_LIBREPCB,
        "chat_fallback_log": CHAT_FALLBACK_LOG, "chat_hanja_table": CHAT_HANJA_TABLE,
        "route_doc_min_score": ROUTE_DOC_MIN_SCORE, "route_doc_strong_score": ROUTE_DOC_STRONG_SCORE, "route_followup_max_chars": ROUTE_FOLLOWUP_MAX_CHARS, "route_ellipsis_max_drop": ROUTE_ELLIPSIS_MAX_DROP, "route_doc_min_terms": ROUTE_DOC_MIN_TERMS,
        "chat_keep_draft_on_fail": CHAT_KEEP_DRAFT_ON_FAIL,
        "access_mode": "password" if ACCESS_PASSWORD else "local-only",
        "upload_max_mb": UPLOAD_MAX_MB, "upload_max_sections": UPLOAD_MAX_SECTIONS,
        "upload_max_chunks": UPLOAD_MAX_CHUNKS,
        "llm_providers": LLM_PROVIDERS, "default_provider": DEFAULT_PROVIDER,
        "openai_configured": bool(OPENAI_API_KEY and OPENAI_MODEL),
        "anthropic_configured": bool(ANTHROPIC_API_KEY and ANTHROPIC_MODEL),
        "allow_external_rag": ALLOW_EXTERNAL_RAG,
    }
