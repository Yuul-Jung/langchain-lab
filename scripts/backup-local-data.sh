#!/usr/bin/env bash
# GitHub에 올라가지 않는 로컬 자료를 한 파일로 묶는다 (다른 PC로 옮기거나 보관할 때).
#
#   묶는 것: data/ (문서 목록·평가 자료) · uploads/ (업로드 원본) · .env (비밀번호·API 키·설정)
#   묶지 않는 것: 소스코드(GitHub에 있음) · .venv · Elasticsearch 색인
#               (색인은 옮긴 PC의 문서 관리 화면 "07 · 추출 규칙 변경 반영"에서 다시 만든다)
#
# 사용:
#   bash scripts/backup-local-data.sh --list              # 무엇이 묶이는지만 보기 (파일을 만들지 않음)
#   bash scripts/backup-local-data.sh                     # ~/langchain-lab-backup-날짜-시각.tar.gz 생성
#   bash scripts/backup-local-data.sh /경로/파일.tar.gz   # 지정한 위치에 생성
#
# 주의: 묶음에는 비밀번호와 비공개 문서가 들어 있다. GitHub·클라우드·메신저에 올리지 않는다.
#       이 스크립트는 원본을 지우거나 바꾸지 않는다. 같은 이름의 파일이 있으면 덮어쓰지 않고 멈춘다.
set -euo pipefail

# (시험용) LANGCHAIN_LAB_DIR 로 프로젝트 폴더를 바꿀 수 있다. 기본은 이 스크립트의 상위 폴더.
PROJECT_DIR="${LANGCHAIN_LAB_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
cd "$PROJECT_DIR"

items=()
for name in data uploads .env; do
  if [ -e "$name" ]; then items+=("$name"); fi
done
if [ "${#items[@]}" -eq 0 ]; then
  echo "[안내] 묶을 자료가 없습니다 (data/, uploads/, .env 가 모두 없음): $PROJECT_DIR"
  exit 1
fi

summary() {
  echo "프로젝트 폴더: $PROJECT_DIR"
  for name in "${items[@]}"; do
    if [ -d "$name" ]; then
      printf '  %-9s 파일 %s개 · %s\n' "$name/" "$(find "$name" -type f | wc -l)" "$(du -sh "$name" | cut -f1)"
    else
      printf '  %-9s 파일 1개 (비밀번호·API 키 포함)\n' "$name"
    fi
  done
  for name in data uploads .env; do
    [ -e "$name" ] || echo "  $name 없음 → 건너뜀"
  done
}

if [ "${1:-}" = "--list" ]; then
  echo "[미리보기] 아래 자료가 묶입니다. 파일은 만들지 않았습니다."
  summary
  exit 0
fi

out="${1:-$HOME/langchain-lab-backup-$(date +%Y%m%d-%H%M).tar.gz}"
case "$out" in
  /*) ;;
  *) out="$PWD/$out" ;;
esac
out_dir="$(cd "$(dirname "$out")" 2>/dev/null && pwd)" || { echo "[중단] 저장할 폴더가 없습니다: $(dirname "$out")"; exit 1; }
out="$out_dir/$(basename "$out")"

# 저장소 안에 만들면 실수로 GitHub에 올라갈 수 있다
case "$out" in
  "$PROJECT_DIR"/*) echo "[중단] 프로젝트 폴더 안에는 만들지 않습니다(실수로 GitHub에 올라갈 수 있음). 다른 위치를 지정하세요."; exit 1 ;;
esac
if [ -e "$out" ]; then
  echo "[중단] 같은 이름의 파일이 이미 있습니다. 덮어쓰지 않습니다: $out"
  exit 1
fi

umask 077
tar -czf "$out" "${items[@]}"
chmod 600 "$out"

echo "[완료] 묶음을 만들었습니다: $out ($(du -h "$out" | cut -f1), 본인만 읽을 수 있는 권한)"
summary
cat <<'EOF'

옮긴 PC에서 푸는 순서:
  1. 소스코드와 기본 세팅:  공개 시작 페이지의 "기본 세팅" 명령 (scripts/setup-local.sh)
  2. 묶음 풀기:            tar -xzf 묶음파일.tar.gz -C ~/langchain_web
  3. Elasticsearch 비밀번호: 새 PC의 비밀번호는 다르므로  .venv/bin/python scripts/repair-es-auth.py
  4. 서비스 재시작:         systemctl --user restart langchain-lab
  5. 색인 다시 만들기:      문서 관리 화면 "07 · 추출 규칙 변경 반영" → 변경 미리보기 → "색인 없음" 문서 다시 추출

주의: 이 묶음에는 비밀번호와 비공개 문서가 들어 있습니다. GitHub·클라우드·메신저에 올리지 마세요.
EOF
