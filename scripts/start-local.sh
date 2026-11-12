#!/usr/bin/env bash
# LangChain Lab: start existing local services without reinstalling or deleting data.
# Usage: bash ~/langchain_web/scripts/start-local.sh
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

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
check_port() {
    if port_open "$1"; then printf '  [정상] %s (포트 %s)\n' "$2" "$1"; return 0; fi
    printf '  [확인 필요] %s (포트 %s)\n' "$2" "$1"; return 1
}

printf '\nLangChain Lab · 로컬 서비스 시작 및 점검\n'
printf '기존 PDF·인덱스·.env 설정은 변경하지 않습니다.\n\n'

# Elasticsearch is a system service: no implicit sudo or privilege escalation.
if ! port_open 9200; then
    echo '[안내] Elasticsearch 9200 포트가 닫혀 있습니다.'
    echo '        필요하면 별도 터미널에서: sudo systemctl start elasticsearch'
fi

# LM Studio may have been closed since the last session.
if ! port_open 1234; then
    if command -v lms >/dev/null 2>&1; then
        echo '[시작] LM Studio 로컬 서버'
        if ! lms server start; then
            echo '[안내] LM Studio 서버 자동 시작 실패: LM Studio 앱을 열고 Local Server를 시작하세요.'
        fi
    else
        echo '[안내] lms 명령을 찾지 못했습니다. LM Studio GUI에서 Local Server를 시작하세요.'
    fi
fi

# (추가) 채팅·임베딩 모델 준비: 내려받은 모델이 안 올라가 있으면 올린다 (이미 있으면 건너뜀).
# 비전 모델이 메모리를 차지하고 있으면 채팅 모델을 억지로 올리지 않고 안내만 한다.
CHAT_MODEL="${CHAT_MODEL:-deepseek-r1-distill-qwen-14b}"
EMBED_MODEL="${EMBED_MODEL:-text-embedding-qwen3-embedding-4b}"
if command -v lms >/dev/null 2>&1 && port_open 1234; then
    downloaded="$(lms ls 2>/dev/null || true)"
    loaded="$(lms ps 2>/dev/null || true)"
    for model in "$EMBED_MODEL" "$CHAT_MODEL"; do
        if grep -q -- "$model" <<<"$loaded"; then
            continue
        fi
        if ! grep -q -- "$model" <<<"$downloaded"; then
            echo "[안내] $model 이 내려받아져 있지 않습니다. LM Studio 에서 내려받으세요."
            continue
        fi
        if [[ "$model" == "$CHAT_MODEL" ]] && grep -q -- "qwen3-vl" <<<"$loaded"; then
            echo "[안내] 비전 모델이 올라가 있어 채팅 모델을 올리지 않았습니다. 제3장 작업이 끝났으면:"
            echo "        lms unload qwen3-vl-4b && lms load $CHAT_MODEL"
            continue
        fi
        echo "[시작] $model 로드"
        lms load "$model" || echo "[안내] $model 로드 실패 — lms ps 로 메모리 사용 모델을 확인하세요."
    done
fi

# FastAPI is managed by the user's existing systemd unit.
if systemctl --user cat langchain-lab.service >/dev/null 2>&1; then
    if ! systemctl --user is-active --quiet langchain-lab.service; then
        echo '[시작] FastAPI 사용자 서비스'
        if ! systemctl --user start langchain-lab.service; then
            echo '[안내] FastAPI 시작 실패. journalctl --user -u langchain-lab -n 40 --no-pager'
        fi
    fi
else
    echo '[안내] FastAPI 서비스가 미등록 상태입니다.'
    echo '        기존 프로젝트 최초 설정: bash scripts/update-local.sh'
fi

printf '\n서비스 상태\n'
check_port 8000 'FastAPI' || true
check_port 9200 'Elasticsearch' || true
check_port 1234 'LM Studio' || true
# (추가) 로드된 모델 표시: 비전 모델이 메모리를 차지하면 채팅 모델 로드가 실패할 수 있음
if port_open 1234 && command -v lms >/dev/null 2>&1; then
    printf '\n로드된 모델 (lms ps)\n'
    lms ps 2>/dev/null || echo '  [안내] lms ps 실행 실패'
    echo '  채팅 응답이 실패하면 공개 시작 페이지의 "③ 로컬 프로그램 상태 확인"에서 조치 명령을 확인하세요.'
fi

if port_open 8000; then
    echo
    echo '문서 인덱스·임베딩 연결 진단 (이 요청은 모델을 호출할 수 있습니다):'
    python3 - <<'PY'
import json
from urllib.request import urlopen
try:
    with urlopen("http://127.0.0.1:8000/api/documents/health/status", timeout=90) as response:
        status = json.load(response)
    for key, title in (("elasticsearch", "Elasticsearch"), ("embedding", "Qwen3 임베딩")):
        item = status.get(key, {})
        print("  " + title + ": " + ("정상" if item.get("ok") else item.get("code", "확인 실패")))
except Exception:
    print("  API 진단 요청 실패. 로컬 문서 관리 화면에서 확인하세요.")
PY
    echo
    echo '로컬 채팅: http://127.0.0.1:8000/'
    echo '문서 관리: http://127.0.0.1:8000/documents'
fi

echo
echo '완료: 원본 문서·비밀번호·Elasticsearch 인덱스는 수정하지 않았습니다.'
