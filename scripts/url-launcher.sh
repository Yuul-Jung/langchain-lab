#!/usr/bin/env bash
# langchainlab:// 링크 처리기.
# 공개 시작 페이지의 버튼(예: langchainlab://start)을 누르면 Ubuntu가 이 스크립트를 실행한다.
#
# 보안: 링크 주소는 어느 웹사이트에서나 만들 수 있으므로, 아래 허용 목록의 동작 이름만 받는다.
#       주소의 나머지 부분(경로·인자·쿼리)은 사용하지 않고, 셸에 그대로 넘기지 않는다.
#   start  → scripts/start-local.sh   (서비스·LM Studio 시작, 데이터 변경 없음)
#   update → scripts/update-local.sh  (GitHub main 최신 코드 · 테스트 · 재시작)
#   setup  → scripts/setup-local.sh   (기본 세팅, 다시 실행해도 안전)
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/langchain-lab"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/launcher.log"

url="${1:-}"
# langchainlab://start , langchainlab://start/ , langchainlab:start 모두 허용
action="${url#langchainlab:}"
action="${action#//}"
action="${action%%[/?#]*}"

case "$action" in
  start)  script="start-local.sh";  title="LangChain Lab · 서비스 시작" ;;
  update) script="update-local.sh"; title="LangChain Lab · 업데이트" ;;
  setup)  script="setup-local.sh";  title="LangChain Lab · 기본 세팅" ;;
  *)
    printf '%s 거부된 요청: %q\n' "$(date '+%F %T')" "$url" >>"$LOG"
    command -v notify-send >/dev/null && notify-send "LangChain Lab" "허용되지 않은 실행 요청을 무시했습니다."
    exit 2
    ;;
esac

printf '%s 실행: %s\n' "$(date '+%F %T')" "$action" >>"$LOG"

# 터미널 창 안에서 실행할 명령 (끝나면 Enter로 닫기)
inner="cd $(printf '%q' "$ROOT") && bash scripts/$script; echo; read -r -p '완료. Enter 를 누르면 창이 닫힙니다… ' _"

if [[ "${LANGCHAINLAB_NO_TERMINAL:-}" != "1" ]]; then
  if command -v gnome-terminal >/dev/null; then
    exec gnome-terminal --title="$title" -- bash -c "$inner"
  elif command -v ptyxis >/dev/null; then
    exec ptyxis --new-window -- bash -c "$inner"
  elif command -v x-terminal-emulator >/dev/null; then
    exec x-terminal-emulator -e bash -c "$inner"
  elif command -v xterm >/dev/null; then
    exec xterm -T "$title" -e bash -c "$inner"
  fi
fi

# 터미널을 찾지 못하면 백그라운드로 실행하고 로그에 남긴다 (setup 은 비밀번호 입력이 필요할 수 있어 제외)
if [[ "$action" == "setup" ]]; then
  command -v notify-send >/dev/null && notify-send "LangChain Lab" "터미널을 찾지 못했습니다. 기본 세팅은 터미널에서 직접 실행하세요."
  exit 3
fi
command -v notify-send >/dev/null && notify-send "LangChain Lab" "$title 실행 중 (로그: $LOG)"
cd "$ROOT" && bash "scripts/$script" </dev/null >>"$LOG" 2>&1
