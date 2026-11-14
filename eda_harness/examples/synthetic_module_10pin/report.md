# synthetic_module_10pin — 하네스 리포트

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

- [G3] **WARN** `PART_DATA_UNVERIFIED` U1 (AMS1117-3.3) 파라미터가 시드값 — 구매 부품 데이터시트로 검증 필요

## 하네스가 둔 가정

- `모듈 핀 SDA_IN.vih_min_v` = 2.0 — [assumed] 사유 미기재 (미검증) [합성 시험 사양, 실제 부품 아님]
- `모듈 핀 SDA_IN.vmax_v` = 5.5 — [derived] 사유 미기재 (미검증) [합성 시험 사양, 실제 부품 아님]
- `모듈 핀 SDA_IN를 구동하는 호스트 출력.voh_min_v` = 2.9 — [derived] 사유 미기재 (미검증) [합성 시험 사양, 실제 부품 아님]
- `모듈 핀 SDA_IN를 구동하는 호스트 출력.voh_max_v` = 3.3 — [derived] 사유 미기재 (미검증) [합성 시험 사양, 실제 부품 아님]
- `보내는 쪽.OUT_A.voh_v` = 5.0 — [derived] 사유 미기재 (미검증) [합성 시험 사양, 실제 부품 아님]
- `보내는 쪽.OUT_A.voh_tol` = 0.1 — [derived] 사유 미기재 (미검증) [합성 시험 사양, 실제 부품 아님]
- `보내는 쪽.OUT_A.iout_max_a` = 0.001 — [assumed] 사유 미기재 (미검증) [합성 시험 사양, 실제 부품 아님]
- `signal_max_hz` = 10000 — 사용자/설계자가 지정한 최대 신호 속도 [합성 시험 사양, 실제 부품 아님]
- `모듈 핀 CLK.vih_min_v` = 2.0 — [assumed] 사유 미기재 (미검증) [합성 시험 사양, 실제 부품 아님]
- `모듈 핀 CLK.vmax_v` = 5.5 — [derived] 사유 미기재 (미검증) [합성 시험 사양, 실제 부품 아님]
- `모듈 핀 CLK를 구동하는 호스트 출력.voh_min_v` = 2.9 — [derived] 사유 미기재 (미검증) [합성 시험 사양, 실제 부품 아님]
- `모듈 핀 CLK를 구동하는 호스트 출력.voh_max_v` = 3.3 — [derived] 사유 미기재 (미검증) [합성 시험 사양, 실제 부품 아님]
- `보내는 쪽.OUT_B.voh_v` = 5.0 — [derived] 사유 미기재 (미검증) [합성 시험 사양, 실제 부품 아님]
- `보내는 쪽.OUT_B.voh_tol` = 0.1 — [derived] 사유 미기재 (미검증) [합성 시험 사양, 실제 부품 아님]
- `보내는 쪽.OUT_B.iout_max_a` = 0.001 — [assumed] 사유 미기재 (미검증) [합성 시험 사양, 실제 부품 아님]
- `signal_max_hz` = 10000 — 사용자/설계자가 지정한 최대 신호 속도 [합성 시험 사양, 실제 부품 아님]
- `모듈 핀 EN.vih_min_v` = 2.0 — [assumed] 사유 미기재 (미검증) [합성 시험 사양, 실제 부품 아님]
- `모듈 핀 EN.vmax_v` = 3.6 — [derived] 사유 미기재 (미검증) [합성 시험 사양, 실제 부품 아님]
- `모듈 핀 EN를 구동하는 호스트 출력.voh_min_v` = 2.9 — [derived] 사유 미기재 (미검증) [합성 시험 사양, 실제 부품 아님]
- `모듈 핀 EN를 구동하는 호스트 출력.voh_max_v` = 3.3 — [derived] 사유 미기재 (미검증) [합성 시험 사양, 실제 부품 아님]

## 블록 설계 근거

- **B1 ldo**: part=AMS1117-3.3, vin_v=5.0, pd_worst_w=0.51, why=AMS1117 고정 출력. 데이터시트 최소 Cin/Cout 적용.
- **B2 logic_module**: dividers={'S2': {'r_top_ohm': 3600.0, 'r_bot_ohm': 4300.0, 'vout_worst_min_v': 2.427, 'vout_worst_max_v': 3.0209}, 'S4': {'r_top_ohm': 3600.0, 'r_bot_ohm': 4300.0, 'vout_worst_min_v': 2.427, 'vout_worst_max_v': 3.0209}}, why=핀 역할별로 연결: vcc 범위 확인·디커플링, in 직결 전압 호환 확인, out 최악 조건 분압 탐색. 100nF 디커플링은 설계 관례(데이터시트 요구 아님)
- **P0 power_input**: connector=Conn_01x02, i_total_a=0.33

## BOM

| Refs | Qty | Part | Value | Footprint |
|---|---|---|---|---|
| J1 | 1 | Conn_01x02 | PWR_IN | Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical |
| C1 C2 | 2 | C | 10u/10V | Capacitor_SMD:C_0805_2012Metric |
| U1 | 1 | AMS1117-3.3 | AMS1117-3.3 | Package_TO_SOT_SMD:SOT-223-3_TabPin2 |
| C3 | 1 | C | 22u/6.3V | Capacitor_SMD:C_0805_2012Metric |
| J2 | 1 | Conn_01x10 | MODULE | Connector_PinHeader_2.54mm:PinHeader_1x10_P2.54mm_Vertical |
| J3 | 1 | Conn_01x06 | HOST | Connector_PinHeader_2.54mm:PinHeader_1x06_P2.54mm_Vertical |
| R1 R3 | 2 | R | 3.6k | Resistor_SMD:R_0603_1608Metric |
| R2 R4 | 2 | R | 4.3k | Resistor_SMD:R_0603_1608Metric |
| C4 | 1 | C | 100n/10V | Capacitor_SMD:C_0603_1608Metric |
| C5 | 1 | C | 100n/6.3V | Capacitor_SMD:C_0603_1608Metric |
