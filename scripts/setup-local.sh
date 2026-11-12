#!/usr/bin/env bash
# LangChain Lab 최초 1회 기본 세팅 (여러 번 실행해도 안전).
#
# 공개 시작 페이지의 한 줄 명령:
#   [ -d ~/langchain_web/.git ] || git clone https://github.com/Yuul-Jung/langchain-lab.git ~/langchain_web
#   bash ~/langchain_web/scripts/setup-local.sh
#
# 하는 일: 필수 프로그램 확인 → CA 인증서 확인 → .env(비밀번호) 생성 → update-local.sh
#          (코드·패키지·테스트·서비스) → LM Studio 서버·모델 준비 → 최종 상태 출력
# 하지 않는 일: sudo 자동 실행, 기존 .env·문서·인덱스 변경, 이미 올라간 모델 내리기
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

CHAT_MODEL="${CHAT_MODEL:-deepseek-r1-distill-qwen-14b}"
EMBED_MODEL="${EMBED_MODEL:-text-embedding-qwen3-embedding-4b}"
CA_USER="$HOME/.config/elasticsearch/http_ca.crt"
CA_SYSTEM="/etc/elasticsearch/certs/http_ca.crt"
WARNINGS=()

step() { printf '\n[%s/6] %s\n' "$1" "$2"; }
ok()   { printf '  [정상] %s\n' "$1"; }
warn() { printf '  [확인 필요] %s\n' "$1"; WARNINGS+=("$1"); }
fail() { printf '\n[중단] %s\n' "$1" >&2; exit 1; }

port_open() {
  python3 - "$1" <<'PY'
import socket, sys
try:
    with socket.create_connection(("127.0.0.1", int(sys.argv[1])), timeout=2):
        sys.exit(0)
except OSError:
    sys.exit(1)
PY
}

printf '\nLangChain Lab · 최초 기본 세팅\n'
printf '여러 번 실행해도 안전합니다. 기존 .env·문서·인덱스는 바꾸지 않습니다.\n'

# ---------------------------------------------------------------- 1. 필수 프로그램
step 1 "필수 프로그램 확인"
command -v git >/dev/null || fail "git 이 없습니다: sudo apt install -y git"
command -v python3 >/dev/null || fail "python3 가 없습니다: sudo apt install -y python3"
python3 -c 'import venv, ensurepip' 2>/dev/null ||
  fail "python3-venv 가 없습니다: sudo apt install -y python3-venv"
command -v systemctl >/dev/null || fail "systemctl 이 없습니다 (systemd 사용 Ubuntu 필요)"
ok "git · python3 · venv · systemd"
if command -v lms >/dev/null; then
  ok "LM Studio 명령(lms)"
else
  warn "lms 명령이 없습니다. LM Studio 앱을 한 번 실행한 뒤: ~/.lmstudio/bin/lms bootstrap"
fi
if port_open 9200; then
  ok "Elasticsearch 9200 포트 응답"
else
  warn "Elasticsearch 가 꺼져 있거나 미설치입니다. 설치되어 있다면: sudo systemctl start elasticsearch"
fi

# ---------------------------------------------------------------- 2. CA 인증서
step 2 "Elasticsearch CA 인증서 확인"
if [[ -r "$CA_USER" ]]; then
  ok "$CA_USER"
elif [[ -e "$CA_SYSTEM" ]]; then
  warn "사용자 폴더에 CA 인증서가 없습니다. 다음 명령으로 복사한 뒤 이 스크립트를 다시 실행하세요:
        mkdir -p ~/.config/elasticsearch && sudo install -m 644 -o \"\$USER\" $CA_SYSTEM $CA_USER"
else
  warn "CA 인증서를 찾지 못했습니다 ($CA_SYSTEM). Elasticsearch 설치 상태를 확인하세요."
fi

# ---------------------------------------------------------------- 3. .env
step 3 "Elasticsearch 비밀번호 설정 (.env)"
if [[ -f .env ]]; then
  ok ".env 있음 — 그대로 사용"
elif [[ -t 0 ]]; then
  echo "  .env 가 없어 비밀번호를 한 번 입력받습니다 (화면에 표시되지 않음, Git 추적 제외)."
  python3 scripts/configure-elasticsearch.py || warn ".env 생성 실패"
else
  warn ".env 가 없습니다. 터미널에서 직접: python3 scripts/configure-elasticsearch.py"
fi

# ---------------------------------------------------------------- 4. 코드·패키지·서비스
step 4 "코드 업데이트 · 패키지 · 테스트 · 서비스 등록 (update-local.sh)"
bash scripts/update-local.sh || fail "update-local.sh 실패 — 위 메시지를 확인하세요."

# ---------------------------------------------------------------- 5. LM Studio
step 5 "LM Studio 서버와 모델 준비"
if command -v lms >/dev/null; then
  if ! port_open 1234; then
    echo "  LM Studio 서버 시작"
    lms server start || warn "LM Studio 서버 시작 실패 — 앱에서 Local Server 를 켜세요."
  fi
  downloaded="$(lms ls 2>/dev/null || true)"
  loaded="$(lms ps 2>/dev/null || true)"
  for model in "$EMBED_MODEL" "$CHAT_MODEL"; do
    if grep -q -- "$model" <<<"$loaded"; then
      ok "$model 로드됨"
    elif grep -q -- "$model" <<<"$downloaded"; then
      echo "  $model 로드 중…"
      if lms load "$model"; then
        ok "$model 로드됨"
      else
        warn "$model 로드 실패 — 다른 모델이 GPU 메모리를 차지했는지 'lms ps' 로 확인하세요."
      fi
    else
      warn "$model 이 내려받아져 있지 않습니다. LM Studio 에서 검색해 내려받으세요."
    fi
  done
else
  warn "lms 가 없어 모델 준비를 건너뜁니다."
fi

# ---------------------------------------------------------------- 6. 최종 상태
step 6 "최종 상태 (/api/status)"
python3 - <<'PY' || warn "상태 API 응답 없음 — journalctl --user -u langchain-lab -n 40 --no-pager"
import json
from urllib.request import urlopen
with urlopen("http://127.0.0.1:8000/api/status", timeout=20) as r:
    st = json.load(r)
icon = {"ok": "✅", "warn": "⚠️", "error": "❌"}
for c in st["components"]:
    print(f"  {icon.get(c['level'], '•')} {c['name']:<14} {c['detail']}")
for a in st["advice"]:
    print(f"  → {a['text']}")
    if a.get("command"):
        print(f"    {a['command']}")
PY

echo
if ((${#WARNINGS[@]})); then
  echo "확인이 필요한 항목 ${#WARNINGS[@]}개:"
  for w in "${WARNINGS[@]}"; do printf '  - %s\n' "$w"; done
  echo "조치 후 같은 명령을 다시 실행하세요 (안전하게 반복 가능)."
else
  echo "[완료] 기본 세팅이 끝났습니다."
fi
echo "로컬 채팅:   http://127.0.0.1:8000/"
echo "문서 관리:   http://127.0.0.1:8000/documents"
echo "이후 평소에는: bash ~/langchain_web/scripts/start-local.sh"
