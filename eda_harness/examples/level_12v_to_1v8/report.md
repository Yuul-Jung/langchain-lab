# level_12v_to_1v8 — 하네스 리포트

**최종 상태: PASS**

| Gate | 이름 | 상태 | ERROR | WARN |
|---|---|---|---|---|
| G0 | INTENT | PASS | 0 | 0 |
| G1 | SYNTHESIS | PASS | 0 | 0 |
| G2 | SEMANTIC_ERC | PASS | 0 | 0 |
| G3 | ELECTRICAL | PASS | 0 | 0 |
| G4 | EMIT | PASS | 0 | 0 |
| G5 | ROUNDTRIP | PASS | 0 | 0 |
| G6 | KICAD_ERC | PASS | 0 | 0 |
| G7 | KICAD_LIBRARY | PASS | 0 | 0 |

## 하네스가 둔 가정

- `blocks.B1.params` = 예시 값 — 일반성 확인용 가상 사양 — 실제 부품 아님(미검증)

## 블록 설계 근거

- **B1 level_shift_divider**: r_top_ohm=10000.0, r_bot_ohm=1500.0, vout_worst_min_v=1.4613, vout_worst_max_v=1.6723, why=최악 조건에서 [High 인식 전압, 받는 쪽 최대 전압] 창 안에 들고 창 중앙에 가장 가까운 E24 쌍. 단방향·저속 신호 전용
- **P0 power_input**: connector=Conn_01x02, i_total_a=0.0

## BOM

| Refs | Qty | Part | Value | Footprint |
|---|---|---|---|---|
| J1 | 1 | Conn_01x02 | PWR_IN | Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical |
| C1 | 1 | C | 10u/10V | Capacitor_SMD:C_0805_2012Metric |
| J2 | 1 | Conn_01x02 | SRC | Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical |
| R1 | 1 | R | 10k | Resistor_SMD:R_0603_1608Metric |
| R2 | 1 | R | 1.5k | Resistor_SMD:R_0603_1608Metric |
| J3 | 1 | Conn_01x02 | SNK | Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical |
