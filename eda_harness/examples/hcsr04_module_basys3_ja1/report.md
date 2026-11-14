# hcsr04_module_basys3_ja1 — 하네스 리포트

**최종 상태: PASS**

| Gate | 이름 | 상태 | ERROR | WARN |
|---|---|---|---|---|
| G0 | INTENT | PASS | 0 | 0 |
| G1 | SYNTHESIS | PASS | 0 | 0 |
| G2 | SEMANTIC_ERC | PASS | 0 | 0 |
| G3 | ELECTRICAL | PASS | 0 | 1 |
| G4 | EMIT | PASS | 0 | 0 |
| G5 | ROUNDTRIP | PASS | 0 | 0 |
| G6 | KICAD_ERC | PASS | 0 | 0 |
| G7 | KICAD_LIBRARY | PASS | 0 | 0 |

## 문제 / 경고

- [G3] **WARN** `MODULE_PIN_ORDER_UNVERIFIED` 모듈 핀 순서가 실제 기판에서 확인되지 않음 — 잘못되면 전원 핀 역접속 위험, 제작 전 확인 필요

## 하네스가 둔 가정

- `모듈 핀 TRIG.vih_min_v` = 2.0 — [assumed] 사양서에 입력 인식 전압 없음(10µs 'TTL pulse'만 명시) — TTL 일반값 2.0V 가정 (미검증)
- `모듈 핀 TRIG.vmax_v` = 5.5 — [derived] 입력 한계 사양 없음 — 모듈 전원 최대 5.5V 이내로 가정 (미검증)
- `모듈 핀 TRIG를 구동하는 호스트 출력.voh_min_v` = 2.9 — [derived] DS181 Table 8 LVCMOS33 VOH 최소 = VCCO−0.400, VCCO 3.3V (Basys3 JA) (미검증)
- `모듈 핀 TRIG를 구동하는 호스트 출력.voh_max_v` = 3.3 — [derived] VCCO 3.3V (미검증)
- `보내는 쪽.ECHO.voh_v` = 5.0 — [derived] 사양서에 Echo High 전압 수치는 없고 '5V TTL' 표기와 동작전압 4.5~5.5V(기준 5V)에서 유도 (미검증)
- `보내는 쪽.ECHO.voh_tol` = 0.1 — [derived] 동작전압 4.5~5.5V를 5V 기준 ±10%로 환산 (미검증)
- `보내는 쪽.ECHO.iout_max_a` = 0.001 — [assumed] Echo 출력 구동 전류 사양 없음 — 1mA 보수적 가정 (미검증)
- `signal_max_hz` = 10000 — 사용자/설계자가 지정한 최대 신호 속도
- `모듈.pin_order_verified` = False — 핀 순서를 실제 기판에서 확인하지 못함 (미검증)

## 블록 설계 근거

- **B1 logic_module**: dividers={'S2': {'r_top_ohm': 3600.0, 'r_bot_ohm': 4300.0, 'vout_worst_min_v': 2.427, 'vout_worst_max_v': 3.0209}}, why=핀 역할별로 연결: vcc 범위 확인·디커플링, in 직결 전압 호환 확인, out 최악 조건 분압 탐색. 100nF 디커플링은 설계 관례(데이터시트 요구 아님)
- **P0 power_input**: connector=Conn_01x02, i_total_a=0.02

## BOM

| Refs | Qty | Part | Value | Footprint |
|---|---|---|---|---|
| J1 | 1 | Conn_01x02 | PWR_IN | Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical |
| C1 | 1 | C | 10u/10V | Capacitor_SMD:C_0805_2012Metric |
| J2 | 1 | Conn_01x04 | MODULE | Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Vertical |
| J3 | 1 | Conn_01x03 | HOST | Connector_PinHeader_2.54mm:PinHeader_1x03_P2.54mm_Vertical |
| R1 | 1 | R | 3.6k | Resistor_SMD:R_0603_1608Metric |
| R2 | 1 | R | 4.3k | Resistor_SMD:R_0603_1608Metric |
| C2 | 1 | C | 100n/10V | Capacitor_SMD:C_0603_1608Metric |
