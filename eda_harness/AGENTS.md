# AGENTS.md — 이 저장소에서 일하는 AI 에이전트(및 사람)를 위한 규칙

이 하네스의 목적은 "회로를 그럴듯하게 만드는 것"이 아니라 **틀린 회로가 통과하지 못하게 하는 것**이다.
기능을 추가할 때 아래 규칙을 어기면 그 변경은 거부된다.

## 절대 규칙

1. **LLM은 IntentSpec까지만.** `adapters.py`를 통하지 않고 LLM 출력이 IR·KiCad 파일에 닿는 경로를 만들지 않는다.
2. **IntentSpec과 IR은 닫힌 스키마다.** 새 필드는 `intent.BLOCK_PARAMS` / `checks._TOP,_COMP,_NET`에 먼저 선언한다.
   검증 실패 출력을 "고쳐서" 통과시키지 않는다.
3. **핀 identity는 핀 번호다.** 핀 이름(GND, VBUS)은 중복될 수 있다.
4. **검증은 재계산이다.** G3 검사는 `blocks.*.design`(합성기가 적은 값)을 근거로 쓰지 않는다. 부품 파라미터와 넷 전압으로 다시 계산한다.
5. **fail-closed.** 판단 근거가 없으면 ERROR 또는 BLOCKED. 도구가 없으면 SKIPPED. 어느 경우에도 PASS가 아니다.
6. **기본값은 기록한다.** 사용자가 말하지 않은 값을 채우면 `assumptions`에 field/value/reason을 남긴다.
7. **스키매틱은 직접 편집하지 않는다.** IR을 바꾸고 재생성한다. 사람이 편집한 스키매틱은 `check`로 IR과 대조한다.

## 새 회로 블록(룰팩) 추가 절차 — `docs/extending.md` 참고

1. `intent.BLOCK_PARAMS`에 파라미터와 검증 함수 추가 (단위가 이름에 들어간다: `_v`, `_a`, `_hz`)
2. 필요한 부품을 `library.py`에 추가 (핀 번호·타입·좌표, 출처 `source`, `data_status`)
3. `synth.py`에 `_<block>(b, bid, p, rails)` 작성, `_RULES`에 등록. 선택 근거를 `design["why"]`에
4. `checks.electrical`에 해당 블록의 전기 규칙 추가 — **부품 값에서 재계산**
5. `intent.parse_text`에 인식 규칙 추가 (모호하면 질문)
6. 테스트: 정상 케이스 PASS + 규칙마다 결함 주입 테스트 1개 이상
7. `scripts/mutation_smoke.py`에 새 핵심 검사 뮤턴트 추가 → 생존 0 확인

## 완료 정의

- `cd tests && python -m unittest -q` 전부 통과
- `python scripts/mutation_smoke.py` 생존 뮤턴트 0
- 새 예제가 `PASS_WITHOUT_KICAD_ERC` 이상 (KiCad 있는 환경이면 `PASS`)
