#!/usr/bin/env bash
# GitHub CI 와 같은 조건(내 PC 전용 폴더 data/·uploads/·.env 가 없는 상태)에서 전체 단위 테스트를 돌린다 — 읽기 전용.
# 작업 폴더에서는 통과하는데 data/ 파일에 몰래 의존하는 시험이나 코드(예: 카탈로그가 없는 새 PC에서의 오류)를 찾는다.
# 사용: bash scripts/check-ci-like.sh        (커밋·푸시 전에 실행)
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COPY="$(mktemp -d)"
trap 'rm -rf "$COPY"' EXIT
rsync -a --exclude data --exclude uploads --exclude .venv --exclude .git --exclude education/dist \
      --exclude __pycache__ --exclude .env "$ROOT"/ "$COPY"/
cd "$COPY"
"$ROOT/.venv/bin/python" -m unittest discover -s tests -q
