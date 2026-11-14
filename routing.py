"""통합 채팅(자동 모드)의 처리 방식 판단 — 문서 · 부품 라이브러리 · 일반 대화.

판단은 모델이 아니라 규칙으로 한다(빠르고, 같은 질문이면 같은 결과이고, 이유를 설명할 수 있다).
순서: ① 올려 둔 문서에 근거가 있으면 문서 ② 없고 부품 핀 질문이면 라이브러리 ③ 그 밖은 일반 대화.

'문서에 근거가 있다'의 기준: 1위 검색 결과가 (a) 점수가 문턱 이상이고 (b) 질문의 낱말이 본문에
1개 이상 실제로 들어 있을 것. 벡터 검색은 관련이 없어도 항상 결과를 채워 주므로 점수만으로는 부족하고,
낱말 일치가 0인 결과(예: 부품 이름만 묻는 질문)는 점수가 높아도 문서 근거로 보지 않는다.

문턱의 근거와 한계(2026-11-14): 문서 질문 22개와 문서와 무관한 질문 15개의 1위 점수·낱말 일치로 정했다.
같은 자료로 정한 값이라 실제 오류율은 이보다 나쁠 수 있다. 문턱은 .env(ROUTE_DOC_MIN_SCORE)에서 바꾼다.
"""
from __future__ import annotations

DOCUMENTS, LIBRARY, GENERAL = "documents", "library", "general"
ROUTE_LABEL = {DOCUMENTS: "문서 근거", LIBRARY: "부품 라이브러리", GENERAL: "일반 대화 (문서 근거 없음)"}


def has_document_evidence(sources: list[dict], min_score: float, min_terms: int = 1) -> bool:
    """검색 결과 1위가 문서 근거로 볼 만한가."""
    if not sources:
        return False
    top = sources[0]
    if top.get("source") not in (None, "documents"):
        return False                       # 제1장 실습 문장 같은 대체 근거는 '올려 둔 문서'가 아니다
    return (top.get("score") or 0) >= min_score and len(top.get("matched_terms") or []) >= min_terms


def evidence_strength(sources: list[dict], strong_score: float) -> str:
    """문서 근거가 '강함'인지 '약함'인지. 문턱을 막 넘은 구간은 문서 질문과 오판이 섞여 있어(2026-11-14 측정:
    0.78~0.85 구간에서 문서 질문 약 3개와 문서 아닌 질문 3개가 함께 들어옴) 약함으로 표시해 사용자가 알 수 있게 한다.
    낱말 일치가 1개뿐인 경우도 흔한 낱말 하나(차이·이름 등)로 걸렸을 가능성이 있어 약함으로 본다."""
    if not sources:
        return "weak"
    top = sources[0]
    if (top.get("score") or 0) < strong_score or len(top.get("matched_terms") or []) < 2:
        return "weak"
    return "strong"


def documents_mention(sources: list[dict], tokens: list[str], top: int = 4) -> bool:
    """검색된 문서 조각 중 하나라도 부품 번호를 그대로 담고 있는가 (대소문자 무시)."""
    texts = [str(s.get("text") or "").lower() for s in sources[:top]]
    return any(t.lower() in x for t in tokens for x in texts)


# 후속 질문의 언어적 단서(대용·연결 표현). 짧은 질문이 이 중 하나를 담으면 직전 질문을 이어받는 후속 질문으로 본다.
# 한국어 담화의 일반적 단서이며 특정 질문 세트에 맞춰 정하지 않았다(2026-11-14, 후속 질문 검증 문장을 보기 전에 고정).
# 한계: 지시어가 없는 생략형 후속 질문("비용은?")은 단서가 없어 이어받지 못한다.
import re as _re

FOLLOWUP_MARKERS = _re.compile(
    r"(?:^|\s)(?:그럼|그러면|그리고|그래서|그런데|그건|그게|그거|그것|그곳|그다음|그\s*다음|그\s*부분|그\s*외|그\s*중|거기|"
    r"이건|이게|이거|이것|이\s*중|저건|위의|위\s*내용|앞서|앞에서|방금|아까|다시|계속|또\s|또는|"
    r"자세히|더\s*알려|더\s*설명|예를\s*들어|예시)"
)


def looks_like_followup(question: str) -> bool:
    """짧은 질문이 직전 질문을 가리키는 표현(그럼·그건·방금·자세히 …)을 담고 있는가."""
    return bool(FOLLOWUP_MARKERS.search(question.strip()))
