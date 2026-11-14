"""KiCad 회로설계 자동화 엔진 개발 하네스 (Stage01: 의도 -> Design IR -> 스키매틱).

핵심 원칙
- LLM/비전 모델은 KiCad 파일을 직접 쓰지 않는다. IntentSpec(JSON)만 제안한다.
- 회로는 결정론적 룰팩(blocks.py)이 Design IR로 합성한다.
- 모든 단계는 Gate를 통과해야 하며, Gate는 실행 가능한 검사로만 PASS를 낸다.
- 검사할 수 없는 것은 PASS가 아니라 SKIPPED/BLOCKED다 (fail-closed).
"""

__version__ = "0.1.0"
