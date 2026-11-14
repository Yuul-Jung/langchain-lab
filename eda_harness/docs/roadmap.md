# 로드맵

## Stage01 (이 저장소) — 의도 → 스키매틱
- [x] 닫힌 IntentSpec, 한/영 규칙 파서, LLM·비전 어댑터 계약
- [x] 룰팩 5종, Design IR, G0~G5, kicad-cli G6 정책
- [x] 결함 주입 테스트 + 뮤테이션 스모크
- [ ] **KiCad 실환경 검증**: KiCad 8/9에서 열기, `kicad-cli sch erc` 결과로 `ALLOWED_WARNINGS` 확정
- [x] G7 KiCad 라이브러리 대응(심볼 핀 번호·풋프린트 패드) — 하네스 부품 전수 대조 완료
- [ ] 부품 데이터 VERIFIED 전환 (구매 부품 데이터시트, `source` 링크)
- [x] 룰팩: 범용 레벨 변환 분압기(level_shift_divider) — 수치 사양만 입력, 부품·벤더 이름 없음
- [x] 룰팩: 범용 로직 모듈(logic_module) — 핀 목록(역할 vcc/gnd/in/out/nc)과 핀별 수치 사양, 핀 개수·이름 무관
- [ ] 룰팩 확장: 벅 컨버터(LDO 열 FAIL의 대안), MCU 최소 회로, I2C 풀업, 양방향/고속용 능동 레벨 변환기
- [ ] 다중 LED/다중 부하 등 파서의 다중 인스턴스 인식

## Stage02 — 스키매틱 → PCB
- 넷리스트 → `.kicad_pcb` 풋프린트 배치 (블록 단위 클러스터)
- 라우팅: 외부 오토라우터(FreeRouting) 연동 또는 규칙 기반
- G7 DRC(`kicad-cli pcb drc`), G8 PCB↔IR 넷 라운드트립

## Stage03 — 제조 출력
- 거버/드릴/BOM/CPL 생성 (`kicad-cli pcb export gerbers|drill|pos`)
- G9 거버 넷 일관성, 제조사 DFM 규칙팩
