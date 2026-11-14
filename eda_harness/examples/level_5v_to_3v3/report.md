# level_5v_to_3v3 — 하네스 리포트

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

- `blocks.B1.params.src_tol` = 0.1 — 보내는 쪽 전원 범위 4.5~5.5V(5V 기준 ±10%)에서 유도 — 사양서에 출력 High 전압 자체는 없음
- `blocks.B1.params.src_iout_max_a` = 0.001 — 출력 구동 전류 사양 없음 — 1mA로 보수적 가정(미검증)
- `blocks.B1.params.sink_vih_min_v` = 2.0 — 3.3V LVCMOS 일반값 가정, 실제 받는 칩 데이터시트로 확인 필요(미검증)
- `blocks.B1.params.sink_vmax_v` = 3.45 — 3.3V +5% 보수적 가정, 칩의 절대 최대 정격이 아님(미검증)
- `blocks.B1.params.signal_max_hz` = 10000.0 — 펄스 폭 측정용 저속 신호로 가정(미검증)

## 블록 설계 근거

- **B1 level_shift_divider**: r_top_ohm=3600.0, r_bot_ohm=4300.0, vout_worst_min_v=2.427, vout_worst_max_v=3.0209, why=최악 조건에서 [High 인식 전압, 받는 쪽 최대 전압] 창 안에 들고 창 중앙에 가장 가까운 E24 쌍. 단방향·저속 신호 전용
- **P0 power_input**: connector=Conn_01x02, i_total_a=0.0

## BOM

| Refs | Qty | Part | Value | Footprint |
|---|---|---|---|---|
| J1 | 1 | Conn_01x02 | PWR_IN | Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical |
| C1 | 1 | C | 10u/10V | Capacitor_SMD:C_0805_2012Metric |
| J2 | 1 | Conn_01x02 | SRC | Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical |
| R1 | 1 | R | 3.6k | Resistor_SMD:R_0603_1608Metric |
| R2 | 1 | R | 4.3k | Resistor_SMD:R_0603_1608Metric |
| J3 | 1 | Conn_01x02 | SNK | Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical |
