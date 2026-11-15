"""부품 종류·추천 질문용 LangGraph.  (핀 질문은 kicad_parts.parts_answer, 문서 질문은 rag_graph 가 맡는다)

  START → classify ─(부품 추천 질문 아님)→ END              (answered=False → 호출한 쪽이 기존 흐름으로 보낸다)
              └→ search ─(후보 0건)→ END                    (answered=False)
                    └→ answer → END                         (answered=True)

- classify: 규칙만 쓴다(모델 호출 없음). 질문에 '부품을 묻는 말'(INTENT)이 있고, 온톨로지가 아는 한국어 용어가 있을 때만 통과한다.
  온톨로지 개념은 기본적으로 승인된 것만 쓴다(include_proposed=False). 사람 승인 전 사전을 시험할 때만 True 로 둔다.
- search: deps.find(질문, 개수) → (부품 목록, 쓴 방식). 비면 온톨로지 영어 키워드·분류로 대체('ontology'). 방식은 trace 와 답에 남긴다.
- answer: 모델을 거치지 않고 검색된 부품 값으로 답을 만든다(깨진 한국어·지어낸 부품 방지). 이름·분류·설명·핀 수는 카탈로그 값 그대로.
- 의존성은 모두 인자로 받아 서버·모델 없이 시험할 수 있다. 각 단계는 trace 에 남는다.
"""
from __future__ import annotations

import operator
import re
from dataclasses import dataclass
from typing import Annotated, Callable, Optional, TypedDict

from langgraph.graph import END, START, StateGraph

import kicad_parts as kp
import ontology_graph as og
import part_conditions as pc
import part_values as pv

# 부품을 찾거나 추천해 달라는 말 (너무 넓지 않게: '문서에서' 같은 말이 있으면 통과시키지 않는다)
# 부품을 찾는 말. 맨 '알려줘'는 설명을 묻는 질문에도 흔해서 뺐다(dev 시험에서 'ADC 해상도가 뭔지 알려줘'를 잘못 처리)
INTENT = re.compile(r"부품|추천|후보|종류|모듈|칩|소자|골라|고르|뭐가\s*있|뭐\s*있|무엇이\s*있|있어|있나|있을까|찾아\s*줘|찾아\s*봐|"
                    r"쓸\s*만|뭐\s*쓰|어떤\s*(?:거|게|것)|구해|사야|좋은\s*거|괜찮은|(?<![a-z])ic(?![a-z])", re.I)
# 부품이 아니라 설명·방법을 묻는 말이 같이 있으면 통과시키지 않는다
EXPLAIN = re.compile(r"뭐야|뭔지|뭐\s*하는|하는\s*일|무엇|원리|차이|설명|방법|코드|계산|어떻게|왜\s|의미|역할|도와\s*줘|도와주|"
                     r"요령|노하우|[가-힣]\s*법(?![가-힣])|정리해", re.I)   # 하는 법·구별법(법칙은 제외)
# 부품이 아니라 소프트웨어·소비자 제품·구매·환경을 묻는 말 (부품 관련어가 같이 있어도 부품 추천이 아니다)
NONPART = re.compile(r"개발\s*환경|비밀번호|이어폰|헤드폰|헤드셋|스피커|노트북|스마트폰|(?<![가-힣])앱(?![가-힣])|프로그램|툴|도구|소프트웨어|"
                     r"강의|튜토리얼|예제|코드|펌웨어|라이브러리|키캐드|kicad|풋프린트|시뮬레이션|가격|구매|재고|후기|리뷰|공부|"
                     r"공유기|전기차|전기\s*자동차|설치|비용|무선\s*충전|핀|(?<![a-z])pin(?![a-z])|핀맵|단자|데이터\s*시트|datasheet|규격|스펙|사양|"   # 핀·규격 질문은 핀 조회가 맡는다
                     r"중고|구입|살까|사도\s*(?:돼|되|될)|싸게|배송|직구|"                                   # 구매
                     r"고장|증상|원인|수리|냄새|안\s*(?:돼|되|켜|꺼|붙)|이상(?:해|하게)|튀(?:어|는|요)|"       # 고장·문제 해결
                     r"전구|청소기|가전", re.I)                                                              # 소비자 제품
# 의도어가 없어도 사전에 개념이 있는 짧은 명사구('디지털 가변저항', '트라이악')는 부품을 찾는 말로 본다
SHORT = 30

# '이 부품 말고 비슷한 것'을 찾는 말 (질문에 카탈로그에 있는 부품 이름이 있을 때)
SIMILAR = re.compile(r"같은\s*거|같은\s*것|[A-Za-z0-9]\s*같은|비슷|유사|대체|대신|말고|다른\s*(?:거|것|부품)|호환|또\s*(?:뭐|있)|비교\s*대상|동급|급의", re.I)
# ---- 기준 부품 고정(anchor_lock)이 켜졌을 때만 추가로 보는 '대체' 표현
# 이 낱말들은 '대체 요청일 수 있다'는 넓은 신호일 뿐이다. 2차 판정에서 낱말 하나(replacement·compatible)가 수리·사양 문장을 부품 추천으로
# 잡았고, 문맥 규칙을 덧붙여도 새 대조 문장에서 다시 깨졌다(동료 검토: 대조 탐침 32개 중 30개 통과). 그래서 요청인지의 판단은
# 학습 관문(substitute_gate.py, 부품 번호를 가린 질문의 임베딩)이 하고, 관문을 쓸 수 없으면 원래의 좁은 낱말(SIMILAR)만 받는다.
REPLACE_EXT = re.compile(r"replacements?|alternatives?|substitutes?|equivalents?|drop-?in|compatible|instead\s+of|similar\s+(?:\w+\s+)?to|second\s+sources?|"
                         r"cross[- ]?references?|다른\s*(?:걸|칩|모델|제품|회사|제조사|메이커)|바꾸|바꿀|바꿔|교체|세컨드\s*소스|크로스\s*레퍼런스|대용(?!량)|대치", re.I)
# 대체 요청의 이유·조건으로 쓰인 구절: 관문 낱말(핀·가격·재고·스펙 …)이 들어 있어도 켬에서는 막지 않는다(요청인지는 학습 관문이 가린다)
_REASON_PHRASES = re.compile(
    r"핀\s*(?:투\s*핀|호환|배열(?:이|도)?\s*(?:같|동일))|pin[- ]?(?:to[- ]?pin|compatible)|(?:가격|값)(?:이|도|은)?\s*(?:싼|저렴|비싸|부담|올라|올랐|오르|너무)|"
    r"재고(?:가|도|는)?\s*(?:없|부족|바닥)|(?:스펙|사양|규격)(?:이|도|은)?\s*(?:비슷|같|동일|유사)|고장\s*(?:나서|났는데|났어요?|이라)", re.I)
# 부품 번호 낱말이 대체 표현에 붙어 있는가(모르는 번호 모양 낱말을 '대체를 묻는 부품 번호'로 볼지 정할 때): 번호 뒤 가까이에 대체류 낱말, 또는 번호 앞에 영어 구
_SUB_AFTER = re.compile(r"대체|대신|대용(?!량)|대치|말고|호환|유사|비슷|같은|동급|교체|바꾸|바꿀|바꿔|세컨드\s*소스|크로스\s*레퍼런스|"
                        r"replacements?|alternatives?|substitutes?|equivalents?|second\s+sources?|cross[- ]?references?", re.I)
_SUB_BEFORE = re.compile(r"(?:instead\s+of|replacements?\s+(?:for|of)|alternatives?\s+(?:to|for)|substitutes?\s+for|similar\s+(?:\w+\s+)?to|"
                         r"equivalents?\s+(?:to|of|for)|replace|(?:대체품|대체재|대용|대신|말고)(?:으로|로|에)?)\s*(?:the\s+|an?\s+)?$", re.I)
# 숫자만으로 된 낱말 뒤에 이런 말이 붙으면 부품 번호가 아니다(2024년, 1000개 …)
_COUNT_WORD = re.compile(r"\s*(?:년|개|원|번|호|차|회|배|명|만|천|백|억|종|쪽|장|대|도|분|초|시간|월|일|층|칸|핀|단|비트|세대|퍼센트|%|사이즈|크기|급)")

# 부품 번호처럼 보이지만 조건·규격인 낱말. '카탈로그에 없는 부품 번호' 판단과 기준 부품 후보에서 뺀다(카탈로그에 정확히 같은 이름이 있으면 부품이 우선).
# 낱말 나열 대신 모양 규칙: 수+단위, 수-낱말, 범위, 교류·직류 표기, 규격·판, 패키지(뒤 숫자 1~3자리), 칩 크기.
_UNIT = (r"(?:v|a|w|hz|f|h|ohm|r|s|b|bits?|bps|sps|ch|g|c|k|m|u|mm|cm|nm|um|db|dbm|dbi|ppm|mah|ah|va|rpm|kg|kpa|pa|dps|lux|baud|min|sec|ms|us|ns|"
         r"bytes?|kb|mb|gb|x|vdc|vac|vpp|vrms|pins?|ksps|msps|lsb|deg|awg|p|i|fps)")
_NOT_PART_TOKEN = re.compile(
    r"^(?:\d+(?:\.\d+)?[munpkmg]?" + _UNIT + r"|"                                                         # 3.3V 100mA 16MHz 2200mAh 12VDC 1080p 24AWG
    r"\d+(?:\.\d+)?-?(?:bit|axis|segment|phase|channel|ch|pin|way|pole|digit|port|cell|wire|layer|key|line|step|stage|band|point)s?|"   # 12-bit 6-axis
    r"\d+(?:\.\d+)?v?[-~]\d+(?:\.\d+)?[munpkmg]?" + _UNIT + r"|"                                         # 3.3-5V 2.7V-5.5V
    r"(?:ac|dc)\d+(?:\.\d+)?v|"                                                                           # DC12V AC220V
    r"(?:can|hdmi|pd|qc|usb|bt)-?\d\.\d[a-z]?|usb-?\d|ble-?\d(?:\.\d)?|ddr\d[a-z]?|ip\d{2}[a-z]?|pm\d\.\d|cat\d[a-z]?|aec-?q\d{3}|(?:csi|dsi)-?\d|"
    r"v(?:er)?\d(?:\.\d)+|h\.26\d|wpa\d|utf-?\d+|nema-?\d+|cr\d{4}|ieee-?\d+(?:\.\d+)?[a-z]*|iso-?\d{4,}|mp\d|"                         # 규격·판·크기
    r"(?:[htvwulxde]{0,2}(?:sot|soic|sop|ssop|tssop|msop|qfn|dfn|bga|lga|lqfp|tqfp|qfp|son|sip|dip|plcc|wlcsp|lfcsp|mlf)|"
    r"tsot|pdip|cdip|qsop|vssop|wson|ufbga|do|so|to|sc|sod|smd|tht|d2?pak)-?\d{1,3}[a-z]{0,2}(?:-\d{1,2}[a-z]?)?|d2pak|"              # 패키지
    r"i2c|i2s|i3c|iic|rs-?\d{3}[a-z]?|usb-?c|1-wire|ipv[46]|[2345]g|wi-?fi\d?|802\.\d+[a-z]*|"
    r"cortex-?[amr]\d+\+?|\d+(?:\.\d+)?(?:x|by)\d+(?:\.\d+)?(?:mm)?|[a-z]\d|\d[a-z]|"
    r"0201|0402|0603|0805|1206|1210|1812|2010|2512)$", re.I)      # 칩 부품 크기 코드(부품 이름 앞머리와 우연히 같을 수 있음)
# 사전에 개념이 없어도 부품을 찾는 말이 분명한 짧은 질문(예: '로드셀 증폭용 칩')은 질문 그대로 검색한다
PART_NOUN = re.compile(r"(?<![가-힣])(?:칩|소자|부품)(?![가-힣])|(?<![a-z])ic(?![a-z])", re.I)
NO_CONCEPT = "(사전 밖 부품 질문)"

DOC_WORDS = re.compile(r"문서|자료|pdf|올려|업로드|과제|본문|\d+\s*쪽|페이지", re.I)

BACKEND_LABEL = {"es-semantic": "의미 검색", "file": "낱말 검색", "ontology": "온톨로지 키워드 검색", "catalog-miss": "카탈로그에 없음"}


class PartsState(TypedDict, total=False):
    question: str
    concepts: list[str]
    concept_ids: list[str]
    anchor: dict
    anchor_scope: dict      # 기준 부품 고정: {'function': 기능 id 또는 None, 'library': 라이브러리, 'label': 표시 이름, 'by': 근거}
    abstain: str            # 추측하지 않고 답하지 않은 이유(기준 부품 고정이나 '카탈로그에 없음' 안내가 켜졌을 때만)
    unverified: list[str]   # 카탈로그로는 확인할 수 없는 질문의 조건(차량용 등급·제조사·핀 호환 …). 답에 확인하지 못했다고 밝힌다(기준 부품 고정)
    notice: str             # 부품 목록 대신 그대로 보일 안내문('카탈로그에 없음' 안내가 켜졌고, 대체품을 묻는데 번호가 카탈로그에 없을 때)
    parts: list[dict]
    plain_base: bool        # 분류 체계 이름으로 찾은 질문이 원래도 보조 관문(짧은 부품 질문)으로 답이 나오던 것인지
    functions: list[str]    # 분류 체계의 기능 id(개념 사전에 없는 말을 우리 분류 체계의 이름으로 찾았을 때)
    conditions: list[str]   # 여러 조건 질문: 질문에서 뽑은 조건 이름(부품마다 checks 에 ✓·✗·? 판정)
    backend: str
    answered: bool
    answer: str
    trace: Annotated[list[str], operator.add]


@dataclass
class PartsDeps:
    find: Callable[[str, int], tuple[list[dict], str]]       # (질문, 개수) → (부품 목록, 방식)
    ontology: Optional[object] = None
    include_proposed: bool = False
    limit: int = 5
    catalog: Optional[list] = None   # 부품 목록(영문 부품 이름으로 '비슷한 부품'을 찾을 때 씀)
    expand: bool = False          # 검색어에 개념의 영어 키워드·분류 이름을 덧붙인다(짧은 한국어 질문의 의미 검색 보강)
    semantic_concepts: Optional[Callable[[str], list[str]]] = None   # 문구가 사전과 다를 때 의미가 가까운 개념(문턱 넘는 것만)
    taxonomy: Optional[object] = None   # 분류 체계(parts_taxonomy.Taxonomy). function_rank 가 켜졌을 때만 쓴다
    function_rank: bool = False         # 기능 단위 순위·분류 표시·분류 체계 이름으로 찾기(설정 PARTS_FUNCTION_RANK, 기본 꺼짐)
    bridge: bool = False          # 한·영 다리 사전의 영어 짝을 검색어에 덧붙임(설정 PARTS_BRIDGE, 기본 꺼짐)
    conditions: bool = False      # 여러 조건 질문(인터페이스·전압·패키지 …)을 뽑아 순서·답에 반영(설정 PARTS_CONDITIONS, 기본 꺼짐)
    anchor_lock: bool = False     # 기준 부품 고정(설정 PARTS_ANCHOR_LOCK, 기본 꺼짐): 대체품은 기준 부품의 기능군 안에서만, 모르면 답하지 않음
    substitute_gate: Optional[Callable[[str], Optional[bool]]] = None   # 번호를 가린 질문 → 대체품 추천 요청인가(True·False), 판단 못 하면 None
    unknown_notice: bool = False  # '카탈로그에 없음' 안내(설정 PARTS_UNKNOWN_NOTICE, 기본 꺼짐): 대체품을 묻는 부품 번호가 카탈로그에 없으면 안내문으로 답함
    veto: Optional[Callable[[str], bool]] = None   # 규칙이 부품 질문이라 본 뒤의 보조 거부(학습 모델, parts_gate.veto). True 면 부품 질문 아님


def parts_concepts(question: str, ontology, include_proposed: bool = False, semantic=None) -> list[str]:
    """부품 추천 질문이면 이해한 개념 노드 id 목록, 아니면 빈 목록. 사전에 정확히 맞는 용어가 없으면 semantic(질문)을 시도한다."""
    if ontology is None or DOC_WORDS.search(question) or EXPLAIN.search(question) or NONPART.search(question):
        return []
    if INTENT.search(question):
        exact = og.translate_query(ontology, question, include_proposed)
        return exact or (semantic(question) if semantic else [])
    exact = og.translate_query(ontology, question, include_proposed, skip_risky=True)   # 의도어 없으면 위험 용어 제외
    # 의도어가 없으면 사전에 정확히 맞는 개념이 있고, 질문이 짧고, 문장형(물음표·'알려줘')이 아닐 때만
    q = question.strip()
    return exact if len(q) <= SHORT and not re.search(r"[?？]|알려|말해|가르쳐", q) else []


def plain_parts_request(question: str, ontology) -> bool:
    """사전에 개념이 없을 때의 보조 관문: 짧고, '칩·IC·소자·부품' 같은 부품 명사가 있고, 설명·문서·비부품 말이 없는 질문."""
    q = question.strip()
    if ontology is None or len(q) > SHORT or not PART_NOUN.search(q) or re.search(r"[?？]|알려|말해|가르쳐", q) \
            or DOC_WORDS.search(q) or EXPLAIN.search(q) or NONPART.search(q):   # 문장형 질문은 짧은 명사구 경로와 같은 규칙으로 제외
        return False
    # 사전 용어가 걸리는데(승인 전 개념 포함) 그 개념을 쓰지 않기로 한 경우에는 우회하지 않는다 — 승인 결정을 존중
    return not og.translate_query(ontology, q, include_proposed=True)


def concept_libraries(ontology, concept_ids: list[str]) -> set[str]:
    """개념이 가리키는 KiCad 분류 이름(lib_prefix 로 펼친 것 포함)."""
    if ontology is None:
        return set()
    return {ontology.nodes[n]["label"] for c in concept_ids for n in ontology.neighbors(c)
            if ontology.nodes[n].get("kind") == "library"}


def rerank_by_library(rows: list[dict], libs: set[str]) -> list[dict]:
    """검색 순서는 유지하되, 개념의 분류에 속한 부품을 앞으로(예: 'OP앰프' 질문에 오디오 앰프가 먼저 오지 않게)."""
    if not libs:
        return rows
    lib_of = lambda r: r.get("library") or r.get("lib_id", "").split(":", 1)[0]
    return [r for r in rows if lib_of(r) in libs] + [r for r in rows if lib_of(r) not in libs]


def function_gate(question: str, taxonomy=None) -> bool:
    """분류 체계 이름으로 찾는 길의 관문: 설명·문서·비부품 말이 없고, 부품을 찾는 말(INTENT)이 있거나,
    짧은 명사구의 모든 내용어가 분류 체계 낱말로 덮이면(부품을 찾는 말이 없어도) 받는다. 소비자 제품·잡담은 덮이지 않아 걸러진다."""
    if DOC_WORDS.search(question) or EXPLAIN.search(question) or NONPART.search(question):
        return False
    q = question.strip()
    if INTENT.search(q):
        return True
    return bool(taxonomy is not None and not re.search(r"[?？]|알려|말해|가르쳐", q) and taxonomy.phrase_covered(q))


def _lib_of(p: dict) -> str:
    return p.get("library") or str(p.get("lib_id", "")).split(":", 1)[0]


def part_info(tax, p: dict):
    return tax.classify(_lib_of(p), p.get("name", ""), " ".join(str(p.get(k) or "") for k in ("description", "keywords", "name")).lower())


def annotate_parts(tax, parts: list[dict]) -> list[dict]:
    out = []
    for p in parts:
        info = part_info(tax, p)
        out.append({**p, "taxonomy": {**info, "label": tax.label(info)}} if info else p)
    return out


def replace_intent(question: str, extended: bool = False) -> bool:
    """'비슷한·대체' 부품을 찾는 말이 있고 설명·문서·비부품 말이 없는가.
    extended(기준 부품 고정 켬)면 넓은 신호(REPLACE_EXT)도 받고, '도대체'는 빼고, 이유·조건 구절(핀 호환·가격이 싼 …)은 관문에서 봐준다.
    넓게 받은 것이 정말 요청인지는 부르는 쪽이 학습 관문으로 다시 가린다."""
    if not extended:
        if DOC_WORDS.search(question) or EXPLAIN.search(question) or NONPART.search(question):
            return False
        return bool(SIMILAR.search(question))
    gate = _REASON_PHRASES.sub(" ", question)
    if DOC_WORDS.search(gate) or EXPLAIN.search(gate) or NONPART.search(gate):
        return False
    text = question.replace("도대체", " ")
    return bool(SIMILAR.search(text) or REPLACE_EXT.search(text))


def condition_shaped(token: str, catalog=None) -> bool:
    """전압·패키지·규격 같은 조건 모양의 낱말인가. 카탈로그에 정확히 같은 이름의 부품이 있으면(숫자+글자 하나 꼴은 숫자 부분이 이름이어도) 부품으로 본다."""
    t = token.lower().strip("-_.+")
    if not _NOT_PART_TOKEN.match(t):
        return False
    if catalog:
        base = re.match(r"^(\d{3,})[a-z]$", t)
        names = {t, base.group(1)} if base else {t}
        if any(p["name"].lower() in names for p in catalog):
            return False
    return True


def _in_catalog(t: str, catalog) -> bool:
    """번호 낱말이 카탈로그 부품 이름과 같거나 그 앞머리인가(숫자만인 낱말을 이름 속 어디든 있으면 받는 핀 조회의 느슨한 규칙은 쓰지 않는다)."""
    return any(p["name"].lower().startswith(t) for p in catalog)


def _shorter_names(token: str, catalog) -> list[dict]:
    """주문용 접미사가 붙어 카탈로그 이름보다 긴 번호(LM2596S-5.0, LM358N, BC547B): 구분 기호를 뺀 카탈로그 이름이 그 번호의 앞머리인 부품들(가장 긴 이름만).
    이름 바로 다음 글자가 숫자면 다른 번호다(MAX2320 은 MAX232 가 아니다). 숫자가 든 5자 이상 이름만 본다."""
    raw = token.lower().strip("-_.+")
    nt = kp._norm(raw)

    def next_char(n_len: int) -> str:          # 원문에서 영문·숫자를 n_len 개 지난 바로 다음 글자
        seen = 0
        for i, ch in enumerate(raw):
            if ch.isalnum():
                seen += 1
                if seen == n_len:
                    return raw[i + 1:i + 2]
        return ""
    hits = [(len(n), p) for p in catalog for n in [kp._norm(p["name"])]
            if 5 <= len(n) < len(nt) and nt.startswith(n) and re.search(r"\d", n) and not next_char(len(n)).isdigit()]
    longest = max((length for length, _ in hits), default=0)
    return [p for length, p in hits if length == longest]


def _short_number(t: str, catalog) -> list[dict]:
    """숫자만 적은 줄임 번호(7805, 555): 글자 1~4개 뒤에 그 숫자가 오고 숫자가 더 이어지지 않는 이름(LM7805, NE555)."""
    rx = re.compile(r"^[a-z]{1,4}" + re.escape(t) + r"(?!\d)")
    return [p for p in catalog if rx.match(p["name"].lower())]


def _attached(question: str, start: int, end: int) -> bool:
    """그 낱말이 대체 표현의 대상인가: 낱말 뒤 가까이(문장 부호 전, 36자 안)에 대체류 낱말이 있거나, 낱말 바로 앞이 'instead of' 같은 구."""
    after = question[end:end + 36]
    m = _SUB_AFTER.search(after)
    if m and not re.search(r"[.?!]", after[:m.start()]):
        return True
    return bool(_SUB_BEFORE.search(question[max(0, start - 28):start]))


def part_tokens_in(question: str, catalog) -> list[tuple[str, bool]]:
    """질문에 적힌 부품 번호 낱말과 카탈로그에 있는지 여부. 조건 모양·수량(2024년, 1000개)은 빼고, 같은 계열은 하나로 센다.
    카탈로그에 없는 낱말은 글자와 숫자가 섞인 4자 이상이고 대체 표현에 붙어 있을 때만 번호로 친다(NEMA17·CR2032 같은 규격·크기 낱말을 거른다)."""
    out: list[tuple[str, bool]] = []
    for m in kp._PART_TOKEN.finditer(question):
        token = m.group()
        t = token.lower().strip("-_.+")
        if len(t) < 3 or not re.search(r"\d", t) or condition_shaped(token, catalog):
            continue
        if t.isdigit():
            rest = question[m.end():]
            if _COUNT_WORD.match(rest) and not _SUB_AFTER.match(rest.lstrip()):
                continue                  # 2024년·1000개 는 번호가 아니다. 다만 '7805 대체품'의 '대'는 세는 말이 아니다
            if not _in_catalog(t, catalog) and not (len(t) <= 5 and _attached(question, m.start(), m.end()) and _short_number(t, catalog)):
                continue                  # 숫자만인 낱말은 이름·앞머리이거나, 대체 표현에 붙은 줄임 번호(7805 → LM7805)일 때만
            known = True
        else:
            base = re.match(r"^(\d{3,})[a-z]$", t)        # 4017B·7805A: 숫자 부분이 카탈로그의 정확한 이름이면 그 부품
            known = (_in_catalog(t, catalog) or bool(base and any(p["name"].lower() == base.group(1) for p in catalog))
                     or bool(_shorter_names(t, catalog)))
            if not known and (len(t) < 4 or not _attached(question, m.start(), m.end())):
                continue
        if any(t.startswith(o.lower().strip("-_.+")) or o.lower().strip("-_.+").startswith(t) for o, _ in out):
            continue                      # LM358 과 LM358N 은 같은 계열
        out.append((token, known))
    return out


def mask_numbers(question: str, tokens: list[tuple[str, bool]]) -> str:
    """부품 번호 낱말을 자리표시로 바꾼 글(학습 관문에 넣고, 조건을 뽑을 때 번호 속 글자를 전압으로 읽지 않게 하는 데 쓴다)."""
    out = question
    for name, (token, _known) in zip(("PARTA", "PARTB", "PARTC"), tokens):
        out = out.replace(token, name)
    return out


def catalog_group(token: str, catalog) -> list[dict]:
    """번호 낱말에 해당하는 카탈로그 부품들(정확히 같은 이름이 있으면 그것만, 없으면 그 낱말로 시작하는 이름). 이름이 짧은 순."""
    t = token.lower().strip("-_.+")
    exact = [p for p in catalog if p["name"].lower() == t]
    group = exact or [p for p in catalog if p["name"].lower().startswith(t)]
    base = re.match(r"^(\d{3,})[a-z]$", t)
    if not group and base:
        group = [p for p in catalog if p["name"].lower() == base.group(1)]
    if not group:
        group = _shorter_names(t, catalog)
    if not group and t.isdigit():
        group = _short_number(t, catalog)
    return sorted(group, key=lambda p: (len(p["name"]), p["lib_id"]))


def anchor_group(question: str, catalog, extended: bool = False) -> list[dict]:
    """'비슷한 부품' 질문에서 질문 속 부품 번호와 맞는 카탈로그 부품들(이름이 짧은 순). 없으면 빈 목록. (기준 부품 고정이 꺼졌을 때의 원래 규칙)"""
    if not catalog or not replace_intent(question, extended):
        return []
    for _token, group in kp._candidate_groups(question, catalog):
        return sorted(group, key=lambda p: (len(p["name"]), p["lib_id"]))
    return []


def find_anchor(question: str, catalog, extended: bool = False) -> dict | None:
    """'비슷한 부품' 질문이면 기준이 되는 카탈로그 부품(질문 속 부품 번호와 맞는 것 중 이름이 가장 짧은 것), 아니면 None."""
    group = anchor_group(question, catalog, extended)
    return group[0] if group else None


def unknown_part_tokens(question: str, catalog) -> list[str]:
    """대체 표현에 붙어 있는 부품 번호 모양 낱말 중 카탈로그에 없는 것(글자와 숫자가 섞인 4자 이상, 전압·패키지·규격 모양 제외)."""
    return [token for token, known in part_tokens_in(question, catalog) if not known]


def unknown_notice_text(tokens: list[str]) -> str:
    """대체품을 묻는 부품 번호가 카탈로그에 없을 때의 안내문(모델을 거치지 않는 고정 문구). 번호가 아닐 수도 있으므로 '번호로 보이는'이라고 쓴다."""
    names = ", ".join(f"`{t}`" for t in tokens)
    return "\n".join([
        f"질문에서 부품 번호로 보이는 {names}을(를) KiCad 부품 라이브러리에서 찾지 못해 대체품을 추천하지 않습니다.", "",
        "- 라이브러리에 없는 부품은 어떤 기능인지 확인할 수 없어, 비슷한 부품을 추측해서 답하지 않습니다.",
        "- 번호 표기를 확인해 주세요. 제조사 접두어나 주문용 접미사를 뺀 기본 번호로 다시 물어보면 찾아질 수 있습니다.",
        "- 부품 번호가 아니라면, 또는 기능으로 찾고 싶다면 기능과 조건으로 물어보세요(예: 3.3V 출력 LDO 추천)."])


def anchor_scope(tax, group: list[dict]) -> tuple[dict | None, str]:
    """기준 부품들의 기능군. (범위, 이유): 범위가 None 이면 정할 수 없음(이유에 까닭).
    기능이 근거(이름 규칙·설명 증거·혼합 아닌 라이브러리의 대표 기능)로 정해지면 그 기능, 혼합 라이브러리에서 근거 없이 대표 기능으로만
    떨어지면 같은 라이브러리로 좁힌다(기능은 추측하지 않음). 후보들의 기능이 서로 다르면 정하지 않는다."""
    if tax is None:
        return None, "분류 체계 없음"
    infos = [part_info(tax, p) for p in group]
    if any(i is None for i in infos):
        return None, "일반 라이브러리 부품이라 기능을 정할 수 없음"
    libs = sorted({_lib_of(p) for p in group})
    home = _lib_of(group[0])          # 기준 부품(묶음의 첫 부품)의 라이브러리
    guessed = [i for i in infos if i["mixed"] and i["by"] == "대표 기능"]
    if guessed:
        if len(libs) > 1:
            return None, "혼합 라이브러리 여러 곳에 걸쳐 기능을 정할 수 없음"
        return {"function": None, "library": home, "label": f"{home} 라이브러리(혼합, 기능 미확정)", "by": "같은 라이브러리"}, ""
    fids = sorted({i["function"] for i in infos})
    if len(fids) > 1:
        return None, f"같은 번호의 부품이 여러 기능에 걸침 {fids}"
    return {"function": fids[0], "library": home, "label": tax.label(infos[0]), "by": infos[0]["by"]}, ""


def similar_query(anchor: dict) -> str:
    """기준 부품의 설명·분류 이름·키워드로 만든 검색어(부품 번호 자체는 넣지 않는다 — 번호가 같은 부품만 나오지 않게)."""
    return " ".join(x for x in (anchor.get("description", ""), og.readable_name(anchor.get("library", "")),
                                anchor.get("keywords", "")) if x).strip()


def is_parts_request(question: str, ontology, include_proposed: bool = False) -> list[str]:
    """부품 추천 질문이면 이해한 개념 이름 목록, 아니면 빈 목록."""
    return [ontology.nodes[c]["label"] for c in parts_concepts(question, ontology, include_proposed)]


def expansion_terms(ontology, concept_ids: list[str], limit: int = 6) -> list[str]:
    """개념이 가리키는 영어 키워드와 분류의 읽는 이름(예: Isolator Analog). 검색어 보강용."""
    out: list[str] = []
    for c in concept_ids:
        for n in ontology.neighbors(c):
            d = ontology.nodes[n]
            term = d.get("label") if d.get("kind") == "keyword" else (og.readable_name(d["label"]) if d.get("kind") == "library" else None)
            if term and term not in out:
                out.append(term)
    return out[:limit]


def ontology_search(ontology, concept_ids: list[str], limit: int) -> list[dict]:
    """ES·임베딩 없이 온톨로지로 찾기: 개념이 가리키는 영어 키워드·분류에 속한 카탈로그 부품 (개념마다 번갈아 가져온다)."""
    lists = [og.concept_parts(ontology, c, limit) for c in concept_ids]
    out, seen = [], set()
    for rank in range(limit):
        for rows in lists:
            if rank < len(rows) and rows[rank]["lib_id"] not in seen:
                r = rows[rank]
                seen.add(r["lib_id"])
                out.append({**r, "name": r["lib_id"].split(":", 1)[-1], "library": r["lib_id"].split(":", 1)[0]})
    return out[:limit]


def format_answer(parts: list[dict], backend: str, concepts: list[str], conditions: list[str] | None = None) -> str:
    lines = [f"KiCad 부품 라이브러리에서 찾은 후보입니다 ({BACKEND_LABEL.get(backend, backend)}, 이해한 개념: {', '.join(concepts)})."]
    if conditions:
        lines.append(f"질문의 조건: {', '.join(conditions)} — 부품마다 ✓ 카탈로그에 근거 있음 · ✗ 맞지 않는 값 · ? 카탈로그에 정보 없음")
    lines.append("")
    for i, p in enumerate(parts, 1):
        desc = (p.get("description") or "").strip() or "설명 없음"
        pins = f", 핀 {p['pin_count']}개" if p.get("pin_count") else ""
        lines.append(f"{i}. **{p.get('name', p.get('lib_id', ''))}** (`{p.get('lib_id', '')}`{pins}) — {desc}")
        if p.get("taxonomy"):
            lines.append(f"   분류: {p['taxonomy']['label']}")
        if conditions and p.get("checks"):
            lines.append("   조건: " + " · ".join(f"{k} {v}" for k, v in p["checks"].items()))
    if conditions and any(v == pc.UNKNOWN for p in parts for v in (p.get("checks") or {}).values()):
        lines += ["", "? 표시 조건은 KiCad 라이브러리 값에 없어 확인하지 못했습니다(예: MCU 의 CAN·USB 같은 주변장치는 카탈로그에 없음). 데이터시트로 꼭 확인하세요."]
    lines += ["", "라이브러리 설명 그대로이며, 설계에 쓰기 전에 데이터시트로 확인하세요. 특정 부품의 핀 배치는 부품 번호와 함께 물어보세요."]
    return "\n".join(lines)


def order_by_position(ontology, question: str, concept_ids: list[str]) -> list[str]:
    """개념을 질문에 나온 순서로(한국어는 머리 명사가 끝에 오므로 마지막 개념을 찾는 대상으로 본다)."""
    lowered = question.lower()

    def first_pos(c):
        pos = [m.start() for n in ontology.neighbors(c) if ontology.nodes[n].get("kind") == "term"
               for m in [og._term_regex(ontology.nodes[n]["label"]).search(lowered)] if m]
        return min(pos) if pos else len(question)
    return sorted(concept_ids, key=first_pos)


def build_parts_graph(deps: PartsDeps):
    def classify(state: PartsState) -> PartsState:
        out = rule_classify(state)
        if (out.get("concepts") or out.get("anchor") or out.get("notice")) and deps.veto is not None and deps.veto(state["question"]):
            return {"concepts": [], "concept_ids": [], "anchor": None, "notice": "",
                    "trace": out["trace"] + ["classify: 학습 관문이 부품 질문이 아니라고 판단 → 기존 흐름"]}
        return out

    def rule_classify(state: PartsState) -> PartsState:
        lock, q = deps.anchor_lock, state["question"]
        if lock and deps.catalog:
            # 기준 부품 고정: 넓은 신호 → 번호 낱말 고르기 → 학습 관문(요청인가) → 번호 수·카탈로그 여부에 따라 기능군 고정 / 답하지 않음
            numbers = part_tokens_in(q, deps.catalog) if replace_intent(q, extended=True) else []
            group = catalog_group(numbers[0][0], deps.catalog) if len(numbers) == 1 and numbers[0][1] else []
            if not numbers and replace_intent(q, extended=True):
                group = sorted(kp._phrase_group(q, deps.catalog), key=lambda p: (len(p["name"]), p["lib_id"]))   # 띄어쓰기가 든 이름 전체
            asked = None
            if numbers or group:
                asked = deps.substitute_gate(mask_numbers(q, numbers)) if deps.substitute_gate is not None else None
                if asked is None:
                    asked = replace_intent(q, extended=False)       # 학습 관문을 쓸 수 없으면 원래의 좁은 낱말만 받는다
            if (numbers or group) and not asked:
                # 부품 번호와 대체류 낱말이 함께 있는데 대체품 추천 요청이 아니라고 판단: 그 부품에 대한 다른 질문(수리·사양·사용법)이므로
                # 부품 추천 경로로 답하지 않는다. 아래 일반 개념 경로로 넘기면 기준 부품 자신이나 무관한 부품이 답으로 나갈 수 있다(동료 검토).
                why = "대체품 추천 요청이 아닌 것으로 판단"
                return {"concepts": [], "concept_ids": [], "abstain": why, "trace": [f"classify: 부품 번호와 대체류 낱말이 있으나 {why} → 답하지 않음"]}
            if asked:
                if len(numbers) >= 2:    # 번호가 둘 이상이면 어느 것이 기준인지, 추천 요청인지(호환 여부·차이를 묻는 질문) 정할 수 없다
                    why = f"부품 번호가 둘 이상 {[t for t, _ in numbers]}"
                    return {"concepts": [], "concept_ids": [], "abstain": why, "trace": [f"classify: 비슷한 부품 질문, {why} → 답하지 않음"]}
                if group:
                    anchor = group[0]
                    scope, why = anchor_scope(deps.taxonomy, group)
                    if scope is None:
                        return {"concepts": [], "concept_ids": [], "abstain": why,
                                "trace": [f"classify: 비슷한 부품 질문, 기준 부품 {anchor['lib_id']} — {why} → 답하지 않음"]}
                    return {"anchor": anchor, "anchor_scope": scope, "concepts": [anchor["lib_id"]], "concept_ids": [],
                            "trace": [f"classify: 비슷한 부품 질문, 기준 부품 {anchor['lib_id']}, 기능군 고정 {scope['label']}({scope['by']})"]}
                unknown = [t for t, known in numbers if not known]
                if unknown:      # 대체품을 묻는데 기준 부품 번호가 카탈로그에 없다: 조건 낱말로 다른 기능군을 추측하지 않는다
                    why = f"부품 번호 {unknown} 가 카탈로그에 없음"
                    out = {"concepts": [], "concept_ids": [], "abstain": why, "trace": [f"classify: 비슷한 부품 질문, {why} → 답하지 않음"]}
                    if deps.unknown_notice and replace_intent(q, extended=False):
                        out["notice"] = unknown_notice_text(unknown)
                        out["trace"] = [f"classify: 비슷한 부품 질문, {why} → 추천하지 않고 안내문으로 답함"]
                    return out
        else:
            group = anchor_group(q, deps.catalog)
            anchor = group[0] if group else None
            if anchor:
                return {"anchor": anchor, "concepts": [anchor["lib_id"]], "concept_ids": [],
                        "trace": [f"classify: 비슷한 부품 질문, 기준 부품 {anchor['lib_id']}"]}
            # '카탈로그에 없음' 안내(기준 부품 고정이 꺼져 있을 때): 원래의 대체 표현이 있고, 그 표현에 붙은 번호가 카탈로그에 없고,
            # 학습 관문이 요청이 아니라고 하지 않을 때만 낸다
            if deps.unknown_notice and deps.catalog and replace_intent(q, extended=False):
                numbers = part_tokens_in(q.replace("도대체", " "), deps.catalog)
                unknown = [t for t, known in numbers if not known]
                asked = deps.substitute_gate(mask_numbers(q, numbers)) if (unknown and deps.substitute_gate is not None) else None
                if unknown and asked is not False:
                    why = f"부품 번호 {unknown} 가 카탈로그에 없음"
                    return {"concepts": [], "concept_ids": [], "abstain": why, "notice": unknown_notice_text(unknown),
                            "trace": [f"classify: 비슷한 부품 질문, {why} → 추천하지 않고 안내문으로 답함"]}
        ids = parts_concepts(state["question"], deps.ontology, deps.include_proposed, deps.semantic_concepts)
        concepts = [deps.ontology.nodes[c]["label"] for c in ids]
        overridden = False
        if ids and deps.function_rank and deps.taxonomy is not None and function_gate(state["question"], deps.taxonomy) \
                and not og.translate_query(deps.ontology, state["question"], deps.include_proposed) and deps.taxonomy.question_functions(state["question"]):
            ids, concepts, overridden = [], [], True     # 개념이 임베딩 추측(정확히 맞는 사전 용어 없음)뿐이고 분류 체계 낱말이 정확히 맞으면 분류 체계를 앞세운다
        if not concepts and deps.function_rank and deps.taxonomy is not None and function_gate(state["question"], deps.taxonomy):
            fids = deps.taxonomy.question_functions(state["question"])
            if fids:
                names = [deps.taxonomy.funcs[f]["ko"] for f in fids]
                return {"concepts": names, "concept_ids": [], "functions": fids,
                        "plain_base": overridden or plain_parts_request(state["question"], deps.ontology),
                        "trace": [f"classify: 개념 사전에는 없지만 분류 체계의 기능 이름으로 부품 질문을 찾음, 기능 {names}"]}
        if not concepts and plain_parts_request(state["question"], deps.ontology):
            return {"concepts": [NO_CONCEPT], "concept_ids": [],
                    "trace": ["classify: 사전에 개념은 없지만 부품을 찾는 짧은 질문 → 질문 그대로 검색"]}
        return {"concepts": concepts, "concept_ids": ids,
                "trace": ["classify: " + (f"부품 추천 질문, 개념 {concepts}" if concepts else "해당 없음 → 기존 흐름")]}

    def after_classify(state: PartsState) -> str:
        if state.get("notice"):
            return "notice"
        return "search" if (state.get("concepts") or state.get("anchor")) else "end"

    def notice(state: PartsState) -> PartsState:
        return {"answer": state["notice"], "answered": True, "backend": "catalog-miss", "parts": [],
                "trace": ["answer: 카탈로그에 없는 부품 번호 안내(부품을 추천하지 않음, 모델 호출 없음)"]}

    def search(state: PartsState) -> PartsState:
        anchor = state.get("anchor")
        if anchor:   # 기준 부품과 비슷한 부품: 기준 부품 자신(같은 이름 계열)은 뺀다
            base = anchor["name"].lower()
            scope = state.get("anchor_scope") if deps.anchor_lock else None
            rows, backend = deps.find(similar_query(anchor), deps.limit * 4 if scope else deps.limit + 8)
            other = lambda r: r.get("lib_id") != anchor["lib_id"] and not r.get("name", "").lower().startswith(base)   # noqa: E731
            if scope:    # 기준 부품의 기능군 안에서만. 조건(인터페이스·전압·패키지 …)은 그 안의 순서만 바꾼다
                tax, fid, lib = deps.taxonomy, scope["function"], scope["library"]
                # 같은 기능으로 '근거 있게' 분류된 부품만(혼합 라이브러리에서 근거 없이 대표 기능으로 떨어진 부품은 후보로 쓰지 않는다)
                sure = lambda r: (i := part_info(tax, r)) is not None and i["function"] == fid and not (i["mixed"] and i["by"] == "대표 기능")   # noqa: E731
                inside = sure if fid else (lambda r: _lib_of(r) == lib)
                found = [r for r in rows if other(r) and inside(r)]
                # 조건은 부품 번호를 가린 글에서 뽑는다(번호 속 글자를 전압으로 읽지 않게: ATtiny85V 의 85V)
                plain = mask_numbers(state["question"], part_tokens_in(state["question"], deps.catalog)) if deps.catalog else state["question"]
                conds = pc.parse(plain) if deps.conditions else []
                # 패키지·실장 형태·전원 전압 조건과 분명히 어긋나는 후보는 뺀다(2차 판정: 'DIP 패키지로'에 다른 패키지만 5개 답한 질문이 틀린 답이었다).
                # 전압은 질문이 전원·동작 전압이라고 밝혔을 때만 쓴다(출력·기준 전압일 수 있다)
                hard = [c for c in conds if c.family == "package" or (c.family == "voltage" and pc.is_supply_voltage(plain))] if deps.conditions else []
                hard += pc.parse_mount(plain) if deps.conditions else []
                dropped = [r for r in found if any(pc.contradicts(c, r) or pc.pin_mismatch(c, plain, r) for c in hard)]
                found = [r for r in found if r not in dropped]
                # 기준 부품 자신의 값(극성·고정 전압·통신 방식·대역·재는 것·논리 기능)과 어긋나는 후보는 뺀다. 양쪽 글에 모두 적혀 있고 다를 때만.
                # 3차 판정에서 켬이 낸 틀린 부품의 가장 큰 덩어리였다(고정 출력 −12V 의 자리에 −5V, NPN 의 자리에 PNP).
                info = part_info(tax, anchor) or {}
                mine = pv.values(anchor, info.get("domain", ""), info.get("function", ""))
                theirs = {r.get("lib_id"): pv.values(r, info.get("domain", ""), info.get("function", "")) for r in found}
                clash = [r for r in found if pv.conflicts(mine, theirs[r.get("lib_id")])]
                found = sorted((r for r in found if r not in clash), key=lambda r: -pv.shared(mine, theirs[r.get("lib_id")]))   # 값이 맞는 것이 확인된 후보를 앞에
                # 후보가 모자라도 카탈로그에서 채우지 않는다. 2차 판정 뒤 확인: 채운 부품은 기능 이름만 같고 값(극성·코어 계열)이 다른 것이 섞여
                # 틀린 부품이 된다(예: PNP 트랜지스터의 자리에 NPN). 적게 내는 편이 낫다.
                # 비교 조건("X보다 전류를 더 많이")은 카탈로그 값으로 믿을 만하게 견줄 수 없어 거르지 않고, 확인할 수 없는 조건으로 밝힌다
                unverified = pc.unverifiable(plain) if deps.conditions else []
                if deps.conditions and pc.has_comparison(plain):
                    unverified.append("기준 부품과 견주는 조건(더 큰·더 낮은 …)")
                parts = (pc.rank(conds, found) if conds else found)[:deps.limit]
                parts = annotate_parts(tax, parts)
                note = ((f"(조건에 어긋나 뺀 후보 {len(dropped)}건)" if dropped else "") + (f"(기준 부품의 값과 어긋나 뺀 후보 {len(clash)}건)" if clash else "")
)
                out = {"parts": parts, "backend": backend if parts else None, "conditions": [c.label for c in conds],
                       "unverified": unverified,
                       "trace": [f"search[{backend}]: 기능군 고정 {scope['label']} 안에서 {len(parts)}건{note}"]}
                if not parts:        # 답하지 않는 이유를 남긴다(집계에서 '일부러 답하지 않음'으로 세어지게)
                    out["abstain"] = (f"질문의 조건({', '.join(c.label for c in hard)})에 맞는 후보가 기능군 안에 없음" if dropped
                                      else (f"기준 부품의 값({', '.join(sorted(mine))})이 같은 후보가 기능군 안에 없음" if clash
                                            else "기능군 안에 다른 후보가 없음"))
                return out
            parts = [r for r in rows if other(r)][:deps.limit]
            if deps.function_rank and deps.taxonomy is not None:
                parts = annotate_parts(deps.taxonomy, parts)
            return {"parts": parts, "backend": backend, "trace": [f"search[{backend}]: 비슷한 부품 {len(parts)}건"]}
        tax = deps.taxonomy if deps.function_rank else None
        fids = state.get("functions") or []
        if fids and tax is not None:     # 분류 체계의 기능 이름으로 찾은 질문
            names = " ".join(tax.funcs[f]["en"] for f in fids)
            rows, backend = deps.find(f"{state['question']} {names}", deps.limit * 8)
            want = set(fids)
            hit = [r for r in rows if (i := part_info(tax, r)) and i["function"] in want]
            added = 0
            if len(hit) < deps.limit and deps.catalog:     # 검색 결과에 그 기능 부품이 모자라면 카탈로그에서 결정적으로 채운다
                have = {r.get("lib_id") for r in hit}
                idx = tax.index(deps.catalog)
                extra = sorted((p for f in fids for p in idx.get(f, []) if p.get("lib_id") not in have),
                               key=lambda p: (not p.get("datasheet"), -(p.get("pin_count") or 0), p["name"]))
                added = len(extra[:deps.limit - len(hit)])
                hit += extra[:deps.limit - len(hit)]
            if state.get("plain_base"):
                # 원래도 보조 관문으로 답이 나오던 질문: 원래 검색 결과(앞쪽 3개)를 지키고 기능 부품을 뒤쪽에 끼워 넣는다(원래 답을 깎지 않는다)
                base, _ = deps.find(state["question"], deps.limit)
                keep = base[:max(deps.limit - 2, 1)]
                seen = {r.get("lib_id") for r in keep}
                parts = keep + [r for r in hit if r.get("lib_id") not in seen][:deps.limit - len(keep)]
            else:
                parts = hit[:deps.limit]
            parts = annotate_parts(tax, parts[:deps.limit])
            return {"parts": parts, "backend": backend if parts else None, "functions": fids,
                    "trace": [f"search[{backend}]: 기능 {fids} 부품 {len(parts)}건(카탈로그 보충 {added}건)"]}
        query = state["question"]
        ids = state.get("concept_ids", [])
        if deps.conditions and deps.ontology is not None and len(ids) > 1:
            ids = order_by_position(deps.ontology, query, ids)
            ids = ids[-1:] + ids[:-1]          # 찾는 대상(마지막 개념)을 앞에, 나머지는 조건
        conds = pc.parse(query, deps.ontology, ids) if deps.conditions else []
        if deps.expand:   # 덧붙일 낱말 순서는 원래 개념 순서(상한 6개 안에서 바뀌지 않게) + 조건 낱말
            extra = expansion_terms(deps.ontology, state.get("concept_ids", [])) + [w for c in conds for w in c.words]
            if deps.bridge:
                import bridge_terms
                extra += bridge_terms.english_for(state["question"])
            query = f"{query} {' '.join(dict.fromkeys(extra))}".strip() if extra else query
        # 분류·후보 수는 조건이 없을 때와 같게 둔다(세트 10에서 찾는 대상만 앞세우자 단일 개념 질문의 적중이 떨어짐 — 2026-11-14).
        # 조건은 같은 후보 안에서 순서만 바꾼다: 분류에 든 부품 중 조건을 더 채운 것이 먼저.
        libs = concept_libraries(deps.ontology, ids)
        rows, backend = deps.find(query, deps.limit * 4 if libs else deps.limit)
        rows = rerank_by_library(rows, libs)
        if conds:
            lib_of = lambda r: r.get("library") or r.get("lib_id", "").split(":", 1)[0]
            in_lib = [r for r in rows if lib_of(r) in libs] if libs else rows
            rows = pc.rank(conds, in_lib) + [r for r in rows if r not in in_lib] if in_lib else pc.rank(conds, rows)
        parts = rows[:deps.limit]
        if tax is not None:
            parts = annotate_parts(tax, parts)
        if not parts:   # ES·임베딩이 안 되고 한국어 낱말 검색도 비면: 온톨로지의 영어 키워드·분류로 대체
            parts = ontology_search(deps.ontology, ids, deps.limit)
            parts = pc.rank(conds, parts) if conds else parts
            backend = "ontology" if parts else backend
        labels = [c.label for c in conds]
        note = f", 조건 {labels}" if labels else ""
        return {"parts": parts, "backend": backend, "conditions": labels, "trace": [f"search[{backend}]: {len(parts)}건{note}"]}

    def after_search(state: PartsState) -> str:
        return "answer" if state.get("parts") else "end"

    def answer(state: PartsState) -> PartsState:
        anchor = state.get("anchor")
        text = format_answer(state["parts"], state["backend"], state["concepts"], state.get("conditions"))
        if anchor:
            scope = state.get("anchor_scope")
            note = f"`{anchor['lib_id']}`와 같은 기능군({scope['label']}) 안에서 설명이 비슷한 부품" if scope else f"`{anchor['lib_id']}`와 설명이 비슷한 부품"
            text = text.replace("찾은 후보입니다", f"찾은 후보입니다 — {note}(성능·핀 호환은 보장하지 않음)", 1)
            if scope and state.get("unverified"):
                text += ("\n\n질문의 조건 중 **" + ", ".join(state["unverified"]) + "**은(는) KiCad 라이브러리 값으로는 확인할 수 없습니다. "
                         "후보는 기능과 확인할 수 있는 조건만으로 골랐으니, 이 조건은 데이터시트나 판매처에서 직접 확인하세요.")
        return {"answer": text, "answered": True, "trace": ["answer: 검색된 부품 값으로 답함 (모델 호출 없음)"]}

    g = StateGraph(PartsState)
    for name, fn in [("classify", classify), ("search", search), ("answer", answer), ("notice", notice)]:
        g.add_node(name, fn)
    g.add_edge(START, "classify")
    g.add_conditional_edges("classify", after_classify, {"search": "search", "notice": "notice", "end": END})
    g.add_edge("notice", END)
    g.add_conditional_edges("search", after_search, {"answer": "answer", "end": END})
    g.add_edge("answer", END)
    return g.compile()


def ask_parts(graph, question: str) -> PartsState:
    return graph.invoke({"question": question, "answered": False, "trace": []})
