# 아키텍처

## 데이터 흐름과 책임

| 단계 | 모듈 | 입력 → 출력 | 누가 결정하나 |
|---|---|---|---|
| 의도 해석 | `intent.py`, `adapters.py` | 자연어/LLM/이미지 → IntentSpec | 파서 또는 모델 (검증됨) |
| 합성 | `synth.py` | IntentSpec → Design IR | 결정론적 룰팩 |
| 검증 | `checks.py` | IR → findings | 규칙 |
| 출력 | `kicad_writer.py` | IR → .kicad_sch, .kicad_sym, .kicad_pro | 결정론적 |
| 대조 | `kicad_reader.py` | .kicad_sch → 연결 그래프 → IR과 비교 | 독립 리더 |
| 외부 ERC | `kicad_cli.py` | .kicad_sch → kicad-cli JSON → 정책 평가 | KiCad |
| 오케스트레이션 | `gates.py`, `cli.py` | Gate 순서, 증거, 리포트 | — |

## Gate

| Gate | PASS 조건 | 실패 시 |
|---|---|---|
| G0 INTENT | IntentSpec 닫힌 스키마 통과, BLOCKING 질문 없음 | FAIL / BLOCKED |
| G1 SYNTHESIS | 룰팩 합성 성공, IR 구조 검사 통과 | FAIL |
| G2 SEMANTIC_ERC | 핀 전부 연결 또는 NC(사유), refdes/풋프린트/값, 넷 ≥2핀, ERC 매트릭스, 외부 전원 PWR_FLAG | FAIL |
| G3 ELECTRICAL | 블록별 전기 규칙 (부품 값에서 재계산) | FAIL — KiCad 파일 생성 안 함 |
| G4 EMIT | 파일 생성 | — |
| G5 ROUNDTRIP | 디스크의 .kicad_sch를 다시 읽은 연결 그래프 = IR (넷 이름·멤버, NC, 부품, 값, 풋프린트, EDA_ID) | FAIL |
| G6 KICAD_ERC | kicad-cli ERC 오류 0, 경고는 허용 목록만 | FAIL / SKIPPED |

최종 상태: 모두 PASS → `PASS`, G6만 SKIPPED → `PASS_WITHOUT_KICAD_ERC`, BLOCKED 있음 → `BLOCKED`, 그 외 `FAIL`.
앞 Gate가 PASS가 아니면 뒤는 `NOT_RUN`.

각 Gate 기록은 `input_sha256` / `output_sha256`(정규화 JSON 또는 파일 텍스트의 sha256)을 가진다.
G1 출력 해시 = G2·G3 입력 해시, G4 출력 해시 = G5 입력 해시가 테스트로 강제된다.

## Design IR (eda.ir/1)

```json
{
  "schema": "eda.ir/1",
  "project": {"name": "usb_ldo"},
  "intent_sha256": "…",
  "assumptions": [{"field": "…", "value": 0.3, "reason": "…"}],
  "nets": {"+3V3": {"kind": "power", "voltage_v": 3.3, "external_supply": false, "current_a": 0.0019}},
  "components": {
    "B1.U": {"id": "B1.U", "ref": "U1", "part": "AMS1117-3.3", "value": "AMS1117-3.3",
             "footprint": "Package_TO_SOT_SMD:SOT-223-3_TabPin2", "block": "B1", "role": "U",
             "params": {"vout_v": 3.3, "dropout_v": 1.3, "…": "…"},
             "pins": {"3": "+5V", "2": "+3V3", "1": "GND"}, "no_connect": {}}
  },
  "blocks": {"B1": {"type": "ldo", "params": {"…": "…"}, "design": {"pd_worst_w": 0.51, "why": "…"}}}
}
```

- 컬렉션은 id-keyed map (`/components/B1.U` 로 안정적 주소 지정).
- 컴포넌트 identity는 `id`(`블록.역할`), `ref`(U1)는 표시용. 스키매틱에는 숨김 속성 `EDA_ID`로 들어가 라운드트립에서 대조된다.
- 전원 넷 이름은 전압에서 유도 (`+3V3`), 불일치 시 `POWER_NET_NAME` 오류.
- `current_a`는 그 넷에서 끌어가는 최악 부하 합계 (LDO 입력에는 설계 출력전류 + 대기전류).

## KiCad 출력 방식

- KiCad 8 포맷(`version 20231120`). 심볼은 `lib_symbols`에 임베드 + `eda.kicad_sym` 프로젝트 라이브러리.
- 모든 심볼 회전 0, 1.27mm 격자. 핀마다 2.54mm 스텁 와이어 + 로컬 라벨. 미사용 핀은 `no_connect`.
- UUID는 `uuid5(프로젝트, 요소키)`로 결정론적 → 같은 IR이면 같은 바이트.
- 리더는 파일에 임베드된 심볼 정의로 핀 좌표를 다시 계산하고 union-find로 연결을 만든다.
  회전/미러/글로벌 라벨은 Stage01 리더가 지원하지 않으므로 발견 시 ERROR (모르는 것을 통과시키지 않음).
