# 명세 1 묶음 분할과 칸 계산 기록 (jung-f1, 위임, 2026-11-15 09:49, 질문 작성 전)

## 고정 사항 (질문을 쓰기 전에 기록, 이후 바꾸지 않음)
- 분할 단위: 부품 질문은 **D×B 묶음 55개**(D 기능 묶음 11 × B 문장 틀 5), 부품 아닌 질문(A6)은 **E×B 묶음 25개**(E 하위 종류 5 × B 5), 문서 질문(A5)은 **B 5개 묶음**(연습만, 봉인 기준에는 쓰지 않음 — 설명용).
- D 11 = power · analog · logic · mcu_mem · comm_rf · sensor · drive_em · discrete · passive_conn · module · other_mixed (분류 체계 영역 이름이 아니라 이 명세의 묶음 이름이며, 질문 작성 때 분류 체계를 보지 않는다). B 5 = B1 짧은 명사구 · B2 부품 찾는 말 · B3 완전한 문장 · B4 영문·한글 혼용 · B5 표기 변형. E 5 = E1 소비자 제품 · E2 취미·일상 · E3 동음이의어 · E4 부품 관련어가 든 비부품 · E5 부품과 무관한 설명형.
- **묶음당 질문 수(quota)**: D×B 묶음 7(B1 묶음은 10), E×B 묶음 5(E4 묶음은 18), A5 묶음 7. 의도 배분(D×B, 7): A1 2·A2 2·A3 2·A4 1(B1 묶음 10: A1 4·A2 2·A3 2·A4 2). 조건 수는 각 묶음에서 C2·C3 가 2개 이상. A3 는 두 D 를 섞고 소속은 첫 번째 D 묶음.
- 고정 문구 `spec1-bundle-split-v1`, 순서 = sha256("고정문구|묶음이름") 오름차순. 봉인 = 부품 묶음 18개(연속 18개 창), E×B 묶음 8개(연속 8개 창).
- 층화·칸 조건(해시 확정 전에 기록): ① 봉인 부품 묶음 중 B1 묶음 ≥ 4(B1 칸 봉인 ≥ 40 ≥ 34) ② 봉인이 D 6개 이상·B 5가지 전부에 걸침 ③ 봉인 묶음마다 그 D 와 B 가 각각 연습에 있음 ④ 봉인 E×B 중 E4 묶음 ≥ 2(E4 칸 봉인 ≥ 36), E 4가지 이상 ⑤ 봉인 E×B 묶음의 E 가 연습에 있음. 어기면 고정 문구는 두고 **창을 한 칸씩 뒤로 옮긴다**.
- 봉인 칸 규모(질문 쓰기 전 계산): A2 = 18×2 = 36, A3 = 18×2 = 36, B1 = (봉인 B1 묶음 수)×10 ≥ 40, C2·C3 = 18×2 이상 = 36 이상, A6×E4 = (봉인 E4 묶음 수)×18 ≥ 36. 모두 ≥ 34 로 계획됨(생성 뒤 실제 수로 재확인; 모자라면 그 칸은 설명용).

## 해시 결과
- 부품 묶음: 창 0(첫 18개)이 모든 조건 충족 → 채택(옮김 0회). 봉인 18: analog|B3, analog|B4, comm_rf|B2, comm_rf|B4, discrete|B3, logic|B1, logic|B5, module|B1, module|B4, other_mixed|B1, other_mixed|B2, other_mixed|B3, passive_conn|B3, passive_conn|B4, passive_conn|B5, power|B1, power|B3, sensor|B1.
- E×B 묶음: 창 0~9 가 ④(E4 묶음 ≥ 2) 등을 어겨 **10칸 옮긴 창 10 채택**(옮김 10회). 봉인 8: E1|B1, E1|B2, E1|B5, E2|B2, E3|B2, E4|B3, E4|B5, E5|B3. (E4 봉인 묶음 2개 = E4|B3, E4|B5 → 봉인 E4 질문 36개.)
- 나머지 묶음은 연습.
- 부품 묶음 해시 순서 앞 20개: logic|B1(070740), passive_conn|B5(07799f), passive_conn|B3(0cfce6), discrete|B3(15048a), comm_rf|B2(1ad292), module|B4(1bc193), power|B1(1eedac), other_mixed|B3(1f00a6), logic|B5(2bb5da), power|B3(2c86a7), analog|B3(30f8b1), module|B1(312652), other_mixed|B1(315a9d), passive_conn|B4(328509), comm_rf|B4(3c4b37), sensor|B1(3d8947), analog|B4(3ff803), other_mixed|B2(4077df), module|B5(44007d), power|B5(46fb0b)
- E×B 해시 순서 전체: E3|B3(02d61d), E4|B4(2e41aa), E5|B2(39bf6e), E1|B4(3a7219), E3|B4(4a6106), E2|B1(4f4a6a), E1|B3(4f7e28), E2|B5(5e67c6), E2|B4(66637d), E3|B5(76410b), E1|B1(87f60b), E1|B2(980b89), E5|B3(a2e8e6), E3|B2(b78fa6), E1|B5(c32517), E4|B5(c3abc1), E2|B2(d47dce), E4|B3(d59f87), E5|B5(dc9baa), E3|B1(de7c5e), E5|B4(dec8da), E5|B1(e87c3e), E2|B3(f09808), E4|B1(fc312a), E4|B2(fc5d89)

## 한계
묶음 이름(D 11개)은 분할 직전에 내가 정했고 시각 증명이 없다. E×B 창을 10번 옮긴 것은 E4 묶음을 봉인에 2개 이상 넣기 위한 조건 때문이며, 이 때문에 봉인 E×B 가 해시 순서 앞쪽이 아니라 뒤쪽 창이 됐다(규칙대로지만 기록한다).
