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
# 기준 부품 고정(anchor_lock)이 켜졌을 때만 추가로 받는 '대체' 표현(영어 표현, '다른 걸로', '바꾸다', '교체')
REPLACE_EXT = re.compile(r"replacement|alternative|substitute|equivalent|drop-?in|compatible|instead\s+of|similar\s+to|"
                         r"다른\s*(?:걸|칩|모델|제품)|바꾸|바꿀|바꿔|교체", re.I)
# 부품 번호처럼 보이지만 조건·규격인 낱말(전압·전류·주파수·패키지·인터페이스 이름). '카탈로그에 없는 부품 번호' 판단에서 뺀다
_NOT_PART_TOKEN = re.compile(
    r"^(?:\d+(?:\.\d+)?(?:[munpkmg]?(?:v|a|w|hz|f|h|ohm|r|s|b|bit|bps|sps|ch|g|c|k|m|u|mm|db|dbm|ppm))|"
    r"(?:sot|soic|sop|ssop|tssop|msop|qfn|dfn|bga|lga|lqfp|tqfp|qfp|dip|sip|to|sc|sod|plcc|wlcsp|smd|tht)-?\d+[a-z]?(?:-\d+[a-z]?)?|"
    r"i2c|i2s|i3c|iic|rs-?\d{3}[a-z]?|usb-?\d(?:\.\d)?|usb-?c|1-wire|ipv[46]|[2345]g|wi-?fi\d?|802\.\d+[a-z]*|"
    r"cortex-?[amr]\d+\+?|\d+(?:x|by)\d+|[a-z]\d|\d[a-z]|"
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
    """'비슷한·대체' 부품을 찾는 말이 있고 설명·문서·비부품 말이 없는가. extended 면 영어 표현·'바꾸다'·'교체'도 받는다."""
    if DOC_WORDS.search(question) or EXPLAIN.search(question) or NONPART.search(question):
        return False
    return bool(SIMILAR.search(question) or (extended and REPLACE_EXT.search(question)))


def anchor_group(question: str, catalog, extended: bool = False) -> list[dict]:
    """'비슷한 부품' 질문에서 질문 속 부품 번호와 맞는 카탈로그 부품들(이름이 짧은 순). 없으면 빈 목록."""
    if not catalog or not replace_intent(question, extended):
        return []
    for token, group in kp._candidate_groups(question, catalog):
        if extended and _NOT_PART_TOKEN.match(token.lower().strip("-_.+")):
            continue      # 전압·패키지·인터페이스 이름이 우연히 부품 이름의 앞머리와 같아도 기준 부품으로 삼지 않는다
        return sorted(group, key=lambda p: (len(p["name"]), p["lib_id"]))
    return []


def find_anchor(question: str, catalog, extended: bool = False) -> dict | None:
    """'비슷한 부품' 질문이면 기준이 되는 카탈로그 부품(질문 속 부품 번호와 맞는 것 중 이름이 가장 짧은 것), 아니면 None."""
    group = anchor_group(question, catalog, extended)
    return group[0] if group else None


def unknown_part_tokens(question: str, catalog) -> list[str]:
    """질문에 적힌 부품 번호처럼 보이는 낱말 중 카탈로그에 없는 것(글자와 숫자가 섞인 4자 이상, 전압·패키지·인터페이스 이름 제외)."""
    out = []
    for token in kp._PART_TOKEN.findall(question):
        t = token.lower().strip("-_.+")
        if len(t) < 4 or not re.search(r"\d", t) or not re.search(r"[a-z]", t) or _NOT_PART_TOKEN.match(t):
            continue
        if not kp._candidates(t, catalog) and not any(p["name"].lower().startswith(t) for p in catalog):
            out.append(token)      # 핀 정보가 없어 핀 조회 후보에는 안 잡히는 부품(카탈로그에는 있음)은 '없는 번호'가 아니다
    return out


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
    guessed = [i for i in infos if i["mixed"] and i["by"] == "대표 기능"]
    if guessed:
        if len(libs) > 1:
            return None, "혼합 라이브러리 여러 곳에 걸쳐 기능을 정할 수 없음"
        return {"function": None, "library": libs[0], "label": f"{libs[0]} 라이브러리(혼합, 기능 미확정)", "by": "같은 라이브러리"}, ""
    fids = sorted({i["function"] for i in infos})
    if len(fids) > 1:
        return None, f"같은 번호의 부품이 여러 기능에 걸침 {fids}"
    return {"function": fids[0], "library": libs[0], "label": tax.label(infos[0]), "by": infos[0]["by"]}, ""


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
        lock = deps.anchor_lock
        group = anchor_group(state["question"], deps.catalog, extended=lock)
        anchor = group[0] if group else None
        if anchor and lock:
            scope, why = anchor_scope(deps.taxonomy, group)
            if scope is None:
                return {"concepts": [], "concept_ids": [], "abstain": why,
                        "trace": [f"classify: 비슷한 부품 질문, 기준 부품 {anchor['lib_id']} — {why} → 답하지 않음"]}
            return {"anchor": anchor, "anchor_scope": scope, "concepts": [anchor["lib_id"]], "concept_ids": [],
                    "trace": [f"classify: 비슷한 부품 질문, 기준 부품 {anchor['lib_id']}, 기능군 고정 {scope['label']}({scope['by']})"]}
        if anchor:
            return {"anchor": anchor, "concepts": [anchor["lib_id"]], "concept_ids": [],
                    "trace": [f"classify: 비슷한 부품 질문, 기준 부품 {anchor['lib_id']}"]}
        # 안내문은 원래의 대체 표현(SIMILAR)이 있을 때만 낸다. 넓힌 표현(REPLACE_EXT)은 수리·사양 문장도 잡으므로 안내 없이 답하지 않기만 한다
        notify = deps.unknown_notice and replace_intent(state["question"], extended=False)
        if deps.catalog and (notify or (lock and replace_intent(state["question"], extended=True))):
            unknown = unknown_part_tokens(state["question"], deps.catalog)
            if unknown:      # 대체품을 묻는데 기준 부품 번호가 카탈로그에 없다: 조건 낱말로 다른 기능군을 추측하지 않는다
                why = f"부품 번호 {unknown} 가 카탈로그에 없음"
                out = {"concepts": [], "concept_ids": [], "abstain": why, "trace": [f"classify: 비슷한 부품 질문, {why} → 답하지 않음"]}
                if notify:
                    out["notice"] = unknown_notice_text(unknown)
                    out["trace"] = [f"classify: 비슷한 부품 질문, {why} → 추천하지 않고 안내문으로 답함"]
                return out
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
                fill = []
                if fid and len(found) < deps.limit and deps.catalog:   # 검색 결과가 모자라면 같은 기능 부품으로 결정적으로 채운다(같은 라이브러리·핀 수가 가까운 것 먼저)
                    have, pins = {r.get("lib_id") for r in found}, anchor.get("pin_count") or 0
                    fill = sorted((p for p in tax.index(deps.catalog).get(fid, []) if p.get("lib_id") not in have and other(p) and sure(p)),
                                  key=lambda p: (_lib_of(p) != lib, abs((p.get("pin_count") or 0) - pins), not p.get("datasheet"), p["name"]))
                    fill = [{**p, "filled": True} for p in fill[:deps.limit - len(found)]]
                conds = pc.parse(state["question"]) if deps.conditions else []
                parts = (pc.rank(conds, found) if conds else found)[:deps.limit]
                parts = annotate_parts(tax, parts + fill[:deps.limit - len(parts)])
                return {"parts": parts, "backend": backend if parts else None, "conditions": [c.label for c in conds],
                        "trace": [f"search[{backend}]: 기능군 고정 {scope['label']} 안에서 {len(parts)}건(카탈로그 보충 {sum(1 for p in parts if p.get('filled'))}건)"]}
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
