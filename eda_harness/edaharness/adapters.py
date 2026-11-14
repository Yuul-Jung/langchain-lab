"""LLM/비전 어댑터 계약.

어댑터는 IntentSpec(JSON)만 반환할 수 있다. 하네스는 그 출력을
1) 순수 JSON으로만 파싱하고 2) source를 강제로 덮어쓰고 3) 닫힌 스키마로 검증한다.
검증에 실패한 출력은 고치려 하지 않고 거부한다 (조용한 보정 = 환각 은폐).
"""
from __future__ import annotations

import json
import re
from typing import Callable

from .intent import BLOCK_PARAMS, LDO_VOUTS, LED_COLORS, SCHEMA_ID, validate_intent

MAX_IMAGE_BYTES = 20 * 1024 * 1024
_IMAGE_MAGIC = {b"\x89PNG\r\n\x1a\n": "png", b"\xff\xd8\xff": "jpeg"}


class AdapterError(Exception):
    pass


def intent_prompt(user_text: str) -> str:
    """LLM에게 줄 지시문. 출력 계약을 명시한다."""
    blocks = {k: sorted(v) for k, v in BLOCK_PARAMS.items()}
    return (
        "너는 전자회로 의도 추출기다. 아래 사용자 요청을 IntentSpec JSON 하나로만 답하라.\n"
        "- 부품값, 넷, KiCad 내용은 절대 만들지 마라. 의도만 기술한다.\n"
        "- 모르는 값은 추측하지 말고 questions에 blocking=true로 질문을 넣어라.\n"
        "- 기본값을 쓰면 assumptions에 field/value/reason을 남겨라.\n"
        f"- schema='{SCHEMA_ID}', source={{\"kind\":\"llm\",\"text\":<원문>}}\n"
        "- power_input: {connector: usb_c|dc, voltage_v} 또는 null (usb_c는 5.0V만)\n"
        f"- blocks[].type과 params 키(모두 필수, 추가 키 금지): {json.dumps(blocks)}\n"
        f"- ldo.vout_v ∈ {list(LDO_VOUTS)}, color ∈ {sorted(LED_COLORS)}\n"
        "- rail/rail_in: 'INPUT' 또는 앞에 정의된 ldo 블록 id\n"
        "- 최상위 키: schema, source, power_input, blocks, assumptions, questions, unparsed\n\n"
        f"사용자 요청:\n{user_text}\n"
    )


def _strict_json(raw: str):
    s = raw.strip()
    fence = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", s, re.S)
    if fence:
        s = fence.group(1)
    try:
        return json.loads(s)
    except json.JSONDecodeError as e:
        raise AdapterError(f"LLM 출력이 순수 JSON이 아님: {e}") from None


def intent_from_llm(call: Callable[[str], str], user_text: str) -> dict:
    """call(prompt)->str 형태의 아무 LLM이나 꽂을 수 있다."""
    data = _strict_json(call(intent_prompt(user_text)))
    if isinstance(data, dict):
        data["source"] = {"kind": "llm", "text": user_text}   # 출처 위조 방지
    errs = validate_intent(data)
    if errs:
        raise AdapterError("LLM IntentSpec 스키마 위반: " + "; ".join(errs[:10]))
    return data


def check_image(data: bytes) -> str:
    if len(data) > MAX_IMAGE_BYTES:
        raise AdapterError("이미지가 20MB를 초과")
    for magic, kind in _IMAGE_MAGIC.items():
        if data.startswith(magic):
            return kind
    raise AdapterError("PNG/JPEG만 허용")


def intent_from_image(analyze: Callable[[bytes], dict], data: bytes,
                      min_confidence: float = 0.8) -> dict:
    """비전 어댑터 계약.

    analyze(image_bytes) -> {"intent": IntentSpec, "confidence": {"blocks/B1": 0.93, ...}}
    신뢰도가 min_confidence 미만인 항목은 사용하지 않고 BLOCKING 질문으로 바꾼다.
    """
    check_image(data)
    out = analyze(data)
    if not isinstance(out, dict) or set(out) != {"intent", "confidence"}:
        raise AdapterError("비전 어댑터 출력은 {intent, confidence}여야 함")
    intent, conf = out["intent"], out["confidence"]
    if not isinstance(intent, dict) or not isinstance(conf, dict):
        raise AdapterError("intent/confidence 타입 오류")
    intent["source"] = {"kind": "image", "text": ""}
    kept = []
    for b in intent.get("blocks", []):
        c = conf.get(f"blocks/{b.get('id')}")
        if not isinstance(c, (int, float)):
            raise AdapterError(f"blocks/{b.get('id')}의 confidence 누락")
        if c >= min_confidence:
            kept.append(b)
        else:
            intent.setdefault("questions", []).append({
                "id": f"QV{len(intent.get('questions', [])) + 1}",
                "text": f"이미지에서 {b.get('type')} 블록을 낮은 신뢰도({c:.2f})로 인식했습니다. 맞습니까?",
                "blocking": True})
    intent["blocks"] = kept
    errs = validate_intent(intent)
    if errs:
        raise AdapterError("비전 IntentSpec 스키마 위반: " + "; ".join(errs[:10]))
    return intent
