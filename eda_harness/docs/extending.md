# 확장 가이드 — 예: 전압 분배기 블록 추가

1. **의도 계약** — `intent.py`
   ```python
   BLOCK_PARAMS["divider"] = {"rail": _str, "vout_v": _num(0, 48, lo_open=True),
                              "tolerance": _num(0, 0.1, lo_open=True)}
   ```
2. **파서** — `parse_text`에 "분배|divider" 인식. 출력 전압을 못 찾으면 `ask(...)`.
3. **합성** — `synth.py`
   ```python
   def _divider(b, bid, p, rails):
       rail = rails[p["rail"]]; v = b.voltage(rail)
       r1 = 10e3; r2 = e_nearest(r1 * p["vout_v"] / (v - p["vout_v"]))
       out = b.net(f"N_{bid}_OUT")
       b.resistor(bid, "R_TOP", r1, rail, out); b.resistor(bid, "R_BOT", r2, out, "GND")
       b.load(rail, v / (r1 + r2))
       b.blocks[bid]["design"] = {"why": "R1=10k 고정, R2 E24 최근접"}
   _RULES["divider"] = _divider
   ```
   주의: `N_{bid}_OUT`이 다른 부품에 연결되지 않으면 G2 `NET_SINGLE_PIN`이 난다 —
   출력을 테스트 포인트/헤더로 내보내는 부품까지 블록에 포함시켜야 한다. 이것이 하네스가 의도한 압력이다.
4. **전기 규칙** — `checks.electrical`: R_TOP/R_BOT의 `r_ohm`으로 실제 비율을 **다시 계산**해 `tolerance`와 비교.
5. **테스트** — 정상 PASS, 비율 틀린 저항 주입 → 새 코드 ERROR, 파서 질문 케이스.
6. **뮤테이션** — `scripts/mutation_smoke.py`의 `MUTANTS`에 새 검사 한 줄을 추가하고 생존 0 확인.

## LLM 어댑터 연결

```python
from edaharness.adapters import intent_from_llm
from edaharness import gates

def call(prompt: str) -> str:
    return my_llm_client.complete(prompt)      # 사용하는 LLM SDK로 구현 (JSON 문자열 반환)

intent = intent_from_llm(call, "배터리 9V로 LED 3Hz 점멸")
gates.run(intent, "out", "llm_demo")
```
어댑터는 출력이 순수 JSON이 아니거나 스키마를 하나라도 어기면 `AdapterError`로 거부한다.

## 비전 어댑터 연결

`analyze(image_bytes) -> {"intent": IntentSpec, "confidence": {"blocks/B1": 0.93, ...}}` 를 구현해
`intent_from_image(analyze, data, min_confidence=0.8)`에 넘긴다. 신뢰도 미달 블록은 제거되고 BLOCKING 질문이 된다.
