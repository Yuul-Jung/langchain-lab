# blocked_question — 하네스 리포트

**최종 상태: BLOCKED**

| Gate | 이름 | 상태 | ERROR | WARN |
|---|---|---|---|---|
| G0 | INTENT | BLOCKED | 1 | 0 |
| G1 | SYNTHESIS | NOT_RUN | 0 | 0 |
| G2 | SEMANTIC_ERC | NOT_RUN | 0 | 0 |
| G3 | ELECTRICAL | NOT_RUN | 0 | 0 |
| G4 | EMIT | NOT_RUN | 0 | 0 |
| G5 | ROUNDTRIP | NOT_RUN | 0 | 0 |
| G6 | KICAD_ERC | NOT_RUN | 0 | 0 |
| G7 | KICAD_LIBRARY | NOT_RUN | 0 | 0 |

## 문제 / 경고

- [G0] **ERROR** `INTENT_QUESTION` Q1: 레귤레이터 출력 전압이 명시되지 않았습니다. 몇 V가 필요합니까?

## 답이 필요한 질문 (intent.json을 수정 후 `--intent`로 재실행)

- Q1 (BLOCKING): 레귤레이터 출력 전압이 명시되지 않았습니다. 몇 V가 필요합니까?
