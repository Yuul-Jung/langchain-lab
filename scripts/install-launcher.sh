#!/usr/bin/env bash
# 공개 시작 페이지 버튼(langchainlab://start 등)으로 내 PC 스크립트를 실행할 수 있게
# 현재 사용자 계정에 링크 처리기를 등록한다. 관리자 권한 불필요, 다시 실행해도 안전.
#
# 해제: rm ~/.local/share/applications/langchainlab-launcher.desktop
#       && update-desktop-database ~/.local/share/applications
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
DESKTOP="$APP_DIR/langchainlab-launcher.desktop"
LAUNCHER="$ROOT/scripts/url-launcher.sh"

chmod +x "$LAUNCHER"
mkdir -p "$APP_DIR"

# Exec 경로에 공백이 있으면 큰따옴표로 감싼다 (Desktop Entry 규격)
cat >"$DESKTOP" <<EOF
[Desktop Entry]
Type=Application
Name=LangChain Lab 실행기
Comment=공개 시작 페이지 버튼으로 로컬 서비스 시작·업데이트·세팅
Exec="$LAUNCHER" %u
MimeType=x-scheme-handler/langchainlab;
NoDisplay=true
Terminal=false
EOF

if command -v xdg-mime >/dev/null; then
  xdg-mime default langchainlab-launcher.desktop x-scheme-handler/langchainlab
else
  echo "[안내] xdg-mime 이 없습니다: sudo apt install -y xdg-utils" >&2
  exit 1
fi
command -v update-desktop-database >/dev/null && update-desktop-database "$APP_DIR" 2>/dev/null || true

registered="$(xdg-mime query default x-scheme-handler/langchainlab 2>/dev/null || true)"
if [[ "$registered" == "langchainlab-launcher.desktop" ]]; then
  echo "  [정상] 링크 처리기 등록: langchainlab:// → $LAUNCHER"
  echo "         공개 페이지 버튼을 처음 누르면 Chrome 이 'xdg-open 열기'를 묻습니다. 허용하세요."
else
  echo "  [확인 필요] 링크 처리기 등록을 확인하지 못했습니다 (현재: ${registered:-없음})" >&2
  exit 1
fi
