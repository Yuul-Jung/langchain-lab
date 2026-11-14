# motor_switch — 하네스 리포트

**최종 상태: PASS**

| Gate | 이름 | 상태 | ERROR | WARN |
|---|---|---|---|---|
| G0 | INTENT | PASS | 0 | 0 |
| G1 | SYNTHESIS | PASS | 0 | 0 |
| G2 | SEMANTIC_ERC | PASS | 0 | 0 |
| G3 | ELECTRICAL | PASS | 0 | 2 |
| G4 | EMIT | PASS | 0 | 0 |
| G5 | ROUNDTRIP | PASS | 0 | 0 |
| G6 | KICAD_ERC | PASS | 0 | 0 |
| G7 | KICAD_LIBRARY | PASS | 0 | 0 |

## 문제 / 경고

- [G3] **WARN** `PART_DATA_UNVERIFIED` Q1 (AO3400A) 파라미터가 시드값 — 구매 부품 데이터시트로 검증 필요
- [G3] **WARN** `PART_DATA_UNVERIFIED` D1 (SS34) 파라미터가 시드값 — 구매 부품 데이터시트로 검증 필요

## 블록 설계 근거

- **B1 lowside_switch**: mosfet=AO3400A, mosfet_reason=조건(Vds≥1.5V, Id≤50%, Vctrl≥Rds 규격 Vgs, Pd)을 만족하는 첫 후보, load_connector=Conn_01x02, flyback=SS34, p_cond_w=0.192
- **P0 power_input**: connector=Conn_01x02, i_total_a=2.0

## BOM

| Refs | Qty | Part | Value | Footprint |
|---|---|---|---|---|
| J1 | 1 | Conn_01x02 | PWR_IN | Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical |
| C1 | 1 | C | 10u/25V | Capacitor_SMD:C_0805_2012Metric |
| J2 | 1 | Conn_01x02 | LOAD | Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical |
| Q1 | 1 | AO3400A | AO3400A | Package_TO_SOT_SMD:SOT-23 |
| R1 | 1 | R | 100 | Resistor_SMD:R_0603_1608Metric |
| R2 | 1 | R | 100k | Resistor_SMD:R_0603_1608Metric |
| J3 | 1 | Conn_01x02 | CTRL | Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical |
| D1 | 1 | SS34 | SS34 | Diode_SMD:D_SMA |
