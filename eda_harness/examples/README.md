# 예제 (모두 `--no-kicad`로 생성)

| 폴더 | 입력 | 결과 |
|---|---|---|
| usb_ldo_led | USB-C 5V 입력에서 3.3V LDO로 300mA 출력, 전원 LED 초록색 | PASS_WITHOUT_KICAD_ERC |
| motor_switch | 12V 입력, 12V 모터 2A를 3.3V MCU로 제어 | PASS_WITHOUT_KICAD_ERC |
| blinker_9v | 9V 입력 LED 2Hz 깜빡이 | PASS_WITHOUT_KICAD_ERC |
| fail_thermal | 12V 입력에서 3V3 LDO, 파란 전원 LED | FAIL (G3: LDO 열, LED 여유) — KiCad 파일 없음 |
| blocked_question | 5V 입력 LDO | BLOCKED (G0: 출력 전압 질문) |

각 폴더의 `report.md`부터 보세요. `.kicad_pro`는 KiCad 8 이상에서 열 수 있습니다.
