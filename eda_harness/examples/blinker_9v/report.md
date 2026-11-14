# blinker_9v — 하네스 리포트

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

- [G3] **WARN** `PART_DATA_UNVERIFIED` U1 (NE555P) 파라미터가 시드값 — 구매 부품 데이터시트로 검증 필요

## 하네스가 둔 가정

- `led.color` = red — LED 색상 미지정 — 빨강(Vf≈2.0V)으로 가정

## 블록 설계 근거

- **B1 blinker_555**: ra_ohm=1000.0, rb_ohm=36000.0, ct_f=1e-05, f_target_hz=2.0, f_actual_hz=1.972603, f_error=0.013699, voh_v=7.3, i_led_a=0.004818, p_r_led_w=0.025536, why=f = 1.44 / ((Ra + 2Rb)·C), C는 Rb가 1k~1M에 들도록 큰 값부터 선택
- **P0 power_input**: connector=Conn_01x02, i_total_a=0.014818

## BOM

| Refs | Qty | Part | Value | Footprint |
|---|---|---|---|---|
| J1 | 1 | Conn_01x02 | PWR_IN | Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical |
| C1 C2 | 2 | C | 10u/16V | Capacitor_SMD:C_0805_2012Metric |
| U1 | 1 | NE555P | NE555P | Package_DIP:DIP-8_W7.62mm |
| R1 | 1 | R | 1k | Resistor_SMD:R_0603_1608Metric |
| R2 | 1 | R | 36k | Resistor_SMD:R_0603_1608Metric |
| C3 | 1 | C | 10n/16V | Capacitor_SMD:C_0603_1608Metric |
| C4 | 1 | C | 100n/16V | Capacitor_SMD:C_0603_1608Metric |
| R3 | 1 | R | 1.1k | Resistor_SMD:R_0603_1608Metric |
| D1 | 1 | LED | LED_red | LED_SMD:LED_0603_1608Metric |
