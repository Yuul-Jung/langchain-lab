# eda_harness — KiCad 회로설계 자동화 엔진 개발 하네스 (Stage01)

자연어(또는 이미지) 회로 의도를 받아 **KiCad 8 스키매틱**까지 만들고, 각 단계를 실행 가능한
Gate로 검증하는 하네스입니다. Python 3.10+ 표준 라이브러리만 사용합니다 (KiCad 설치 없이도
G0~G5까지 전부 동작, KiCad가 있으면 G6에서 `kicad-cli` ERC까지 실행).

```
자연어/이미지 ──▶ IntentSpec ──▶ Design IR ──▶ .kicad_sch ──▶ 다시 읽어 IR과 대조 ──▶ kicad-cli ERC
  (파서/LLM/비전)    G0 의도      G1~G3 합성·검증    G4 출력        G5 라운드트립          G6 (선택)
```

## 빠른 시작

```bash
python -m edaharness run --text "USB-C 5V 입력에서 3.3V LDO로 300mA 출력, 전원 LED 초록색" --name usb_ldo --out out
# G0~G5 PASS, G6 SKIPPED(kicad-cli 없음) → 최종 PASS_WITHOUT_KICAD_ERC
# out/usb_ldo/usb_ldo.kicad_pro 를 KiCad 8 이상에서 열면 됩니다.

python -m edaharness parse "12V 입력, 12V 모터 2A를 3.3V MCU로 제어"     # IntentSpec만 보기
python -m edaharness check out/usb_ldo/usb_ldo.kicad_sch --ir out/usb_ldo/design_ir.json

cd tests && python -m unittest -q          # 111개 테스트
python scripts/mutation_smoke.py           # 검사가 실제로 결함을 잡는지 (뮤턴트 14개)
```

종료 코드: `0` PASS / PASS_WITHOUT_KICAD_ERC, `1` FAIL, `2` BLOCKED(질문에 답 필요).

## 산출물 (`out/<name>/`)

| 파일 | 내용 |
|---|---|
| `intent.json` | 해석된 의도. BLOCKED면 여기 질문에 답을 채워 `--intent`로 재실행 |
| `design_ir.json` | 부품·핀·넷·설계 근거가 담긴 단일 진실 원천 (G1 이후) |
| `<name>.kicad_sch` / `.kicad_pro` | KiCad 8 스키매틱/프로젝트 (G3 PASS일 때만 생성) |
| `eda.kicad_sym`, `sym-lib-table` | 프로젝트 로컬 심볼 라이브러리 |
| `bom.csv`, `preview.svg` | BOM, KiCad 없이 보는 미리보기 |
| `gate_report.json`, `report.md` | Gate별 상태·증거 해시·finding, 사람이 읽는 리포트 |

## 지금 지원하는 회로 블록 (룰팩)

| 블록 | 자연어 예 | 하네스가 하는 일 |
|---|---|---|
| 전원 입력 | `USB-C 5V`, `12V 입력` | USB-C(CC 5.1k Rd 자동) 또는 DC 헤더/터미널블록을 전류로 선택, 벌크 캡, PWR_FLAG |
| LDO | `5V에서 3.3V LDO 300mA` | AMS1117-1.8/2.5/3.3/5.0, 데이터시트 최소 Cin/Cout |
| 표시 LED | `전원 LED 초록` | 레일 전압·Vf로 E24 저항 올림 선택 |
| 555 점멸 | `LED 2Hz 깜빡` | Ra/Rb/C 계산, CV·디커플링 캡, 출력 LED |
| 로우사이드 스위치 | `12V 모터 2A를 3.3V MCU로` | MOSFET 후보 선택, 게이트 저항/풀다운, 유도성 부하면 플라이백 다이오드 |

## Gate가 실제로 잡는 것 (예)

- `12V 입력에서 3V3 LDO, 파란 전원 LED` → **G3 FAIL**: LDO 손실 2.61W > 0.94W(벅 필요), 파란 LED 전류제한 여유 0.3V
- `USB 입력에서 3.3V LDO 600mA` → **G3 FAIL**: USB 기본 전력 500mA 초과
- `12V 모터 8A를 3.3V MCU로` → **G3 FAIL**: 3.3V로 완전 도통이 보장되는 후보 MOSFET 없음 (조용히 넘어가지 않음)
- `5V 입력 LDO` → **G0 BLOCKED**: 출력 전압 질문
- 스키매틱을 손으로 고쳐 넷이 바뀌면 → **G5 FAIL** (`check` 명령)

## 설계 원칙 (요약 — 자세히는 `AGENTS.md`, `docs/architecture.md`)

1. LLM/비전 모델은 **IntentSpec만** 출력한다. 부품값·넷·KiCad 파일은 절대 만들지 않는다.
2. 회로는 결정론적 룰팩이 합성한다. 같은 의도 → 바이트 단위로 같은 출력.
3. 검증은 합성기가 적어둔 값을 믿지 않고 **IR의 부품 값에서 다시 계산**한다.
4. 모르면 묻는다(BLOCKED). 기본값을 쓰면 `assumptions`에 남긴다. 인식했지만 분류 못한 숫자는 버리지 않는다.
5. 검사할 수 없는 것은 PASS가 아니다 (kicad-cli 없음 → SKIPPED).
6. G2/G3 실패 설계는 KiCad 파일로 나가지 않는다.

## 한계 (정직하게)

- 이 환경에는 KiCad가 없어 **실제 KiCad에서 열어보거나 kicad-cli ERC를 돌려보지는 못했습니다.**
  파일은 KiCad 8 포맷(version 20231120)을 따르고, 하네스 자체 리더로 라운드트립 검증했습니다.
  KiCad 설치 환경에서 `python -m edaharness run ...` 시 G6가 자동 실행되니, 첫 실행 결과로
  `kicad_cli.ALLOWED_WARNINGS` 정책을 확정하세요.
- 부품 파라미터는 데이터시트 대표값을 옮긴 **시드 데이터**입니다(`PART_DATA_UNVERIFIED` 경고).
- 배치는 블록 격자 + 핀마다 넷 라벨 방식입니다. 연결 정확성은 보장되지만 사람이 그린 도면처럼
  예쁘지는 않습니다.
- 비전 입력은 **어댑터 계약과 신뢰도 정책까지만** 구현되어 있고, 실제 이미지 인식 모델은 꽂아야 합니다.
