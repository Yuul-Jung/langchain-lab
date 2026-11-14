# fail_thermal — 하네스 리포트

**최종 상태: FAIL**

| Gate | 이름 | 상태 | ERROR | WARN |
|---|---|---|---|---|
| G0 | INTENT | PASS | 0 | 0 |
| G1 | SYNTHESIS | PASS | 0 | 0 |
| G2 | SEMANTIC_ERC | PASS | 0 | 0 |
| G3 | ELECTRICAL | FAIL | 2 | 1 |
| G4 | EMIT | NOT_RUN | 0 | 0 |
| G5 | ROUNDTRIP | NOT_RUN | 0 | 0 |
| G6 | KICAD_ERC | NOT_RUN | 0 | 0 |
| G7 | KICAD_LIBRARY | NOT_RUN | 0 | 0 |

## 문제 / 경고

- [G3] **ERROR** `LDO_THERMAL` U1: 손실 2.61W > 허용 0.94W (Ta=40°C, θja=90.0) — 출력 전류를 줄이거나 벅 컨버터가 필요
- [G3] **ERROR** `LED_HEADROOM` D1: 전류제한 여유 0.30V < 0.5V — Vf 편차로 밝기/전류가 크게 변함
- [G3] **WARN** `PART_DATA_UNVERIFIED` U1 (AMS1117-3.3) 파라미터가 시드값 — 구매 부품 데이터시트로 검증 필요

## 하네스가 둔 가정

- `blocks.ldo.iout_max_a` = 0.3 — 출력 전류 미지정 — 300mA로 가정
- `blocks.led_indicator.current_a` = 0.002 — 표시용 LED 전류 2mA 가정

## 블록 설계 근거

- **B1 ldo**: part=AMS1117-3.3, vin_v=12.0, pd_worst_w=2.61, why=AMS1117 고정 출력. 데이터시트 최소 Cin/Cout 적용.
- **B2 led_indicator**: r_ohm=150.0, i_led_a=0.002, headroom_v=0.3, p_r_w=0.0006, why=R = (Vrail - Vf) / I, E24 올림 선택 (전류가 목표 이하)
- **P0 power_input**: connector=Conn_01x02, i_total_a=0.31

## BOM

| Refs | Qty | Part | Value | Footprint |
|---|---|---|---|---|
| J1 | 1 | Conn_01x02 | PWR_IN | Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical |
| C1 C2 | 2 | C | 10u/25V | Capacitor_SMD:C_0805_2012Metric |
| U1 | 1 | AMS1117-3.3 | AMS1117-3.3 | Package_TO_SOT_SMD:SOT-223-3_TabPin2 |
| C3 | 1 | C | 22u/6.3V | Capacitor_SMD:C_0805_2012Metric |
| R1 | 1 | R | 150 | Resistor_SMD:R_0603_1608Metric |
| D1 | 1 | LED | LED_blue | LED_SMD:LED_0603_1608Metric |
