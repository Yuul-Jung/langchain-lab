# usb_ldo_led — 하네스 리포트

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

- [G3] **WARN** `PART_DATA_UNVERIFIED` J1 (USB_C_Power_6P) 파라미터가 시드값 — 구매 부품 데이터시트로 검증 필요
- [G3] **WARN** `PART_DATA_UNVERIFIED` U1 (AMS1117-3.3) 파라미터가 시드값 — 구매 부품 데이터시트로 검증 필요

## 하네스가 둔 가정

- `blocks.led_indicator.current_a` = 0.002 — 표시용 LED 전류 2mA 가정

## 블록 설계 근거

- **B1 ldo**: part=AMS1117-3.3, vin_v=5.0, pd_worst_w=0.51, why=AMS1117 고정 출력. 데이터시트 최소 Cin/Cout 적용.
- **B2 led_indicator**: r_ohm=620.0, i_led_a=0.001935, headroom_v=1.2, p_r_w=0.002323, why=R = (Vrail - Vf) / I, E24 올림 선택 (전류가 목표 이하)
- **P0 power_input**: connector=USB_C_Power_6P, i_total_a=0.31

## BOM

| Refs | Qty | Part | Value | Footprint |
|---|---|---|---|---|
| J1 | 1 | USB_C_Power_6P | USB_C | Connector_USB:USB_C_Receptacle_GCT_USB4125-xx-x_6P_TopMnt_Horizontal |
| R1 R2 | 2 | R | 5.1k | Resistor_SMD:R_0603_1608Metric |
| C1 C2 | 2 | C | 10u/10V | Capacitor_SMD:C_0805_2012Metric |
| U1 | 1 | AMS1117-3.3 | AMS1117-3.3 | Package_TO_SOT_SMD:SOT-223-3_TabPin2 |
| C3 | 1 | C | 22u/6.3V | Capacitor_SMD:C_0805_2012Metric |
| R3 | 1 | R | 620 | Resistor_SMD:R_0603_1608Metric |
| D1 | 1 | LED | LED_green | LED_SMD:LED_0603_1608Metric |
