#!/usr/bin/env bash
# Optional: create a desktop launcher for the LangChain Lab updater.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DESKTOP="$HOME/Desktop"
if [[ ! -d "$DESKTOP" ]]; then
  # Use XDG location if the desktop has a non-English folder name.
  if command -v xdg-user-dir >/dev/null 2>&1; then
    DESKTOP="$(xdg-user-dir DESKTOP)"
  fi
fi
[[ -d "$DESKTOP" ]] || { echo "바탕화면 폴더가 없습니다. 이 설치 단계는 생략합니다."; exit 1; }
FILE="$DESKTOP/LangChain-Lab-업데이트.desktop"

# Desktop-file Exec expects quoted paths. Reject quote/newline to avoid malformed launchers.
if [[ "$ROOT" == *'"'* || "$ROOT" == *$'\n'* ]]; then
  echo "프로젝트 경로에 지원하지 않는 문자가 있습니다."
  exit 1
fi
cat > "$FILE" <<EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=LangChain Lab 업데이트
Comment=GitHub 코드를 받아 검사한 뒤 로컬 FastAPI 서버 재시작
Exec=bash -lc 'cd "$ROOT" && bash scripts/update-local.sh; echo; read -r -p "닫으려면 Enter를 누르세요..."'
Terminal=true
Icon=system-software-update
Categories=Development;
EOF
chmod 755 "$FILE"
echo "바탕화면 실행 아이콘 생성: $FILE"
echo "Ubuntu가 실행 권한을 요구하면 아이콘의 '실행 허용(Allow Launching)'을 선택하세요."
