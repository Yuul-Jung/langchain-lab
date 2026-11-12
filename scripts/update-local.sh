#!/usr/bin/env bash
# LangChain Lab: update source, install dependencies, validate, restart and check.
# Run: bash ~/langchain_web/scripts/update-local.sh
set -Eeuo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_ROOT"

step() { printf '\n[%s/7] %s\n' "$1" "$2"; }
fail() { printf '\n[실패] %s\n' "$1" >&2; exit 1; }

[[ -f requirements.txt && -f app.py ]] || fail "올바른 langchain-lab 프로젝트가 아닙니다."
[[ -d .git ]] || fail "GitHub에서 복제한 Git 프로젝트가 아닙니다."
command -v git >/dev/null || fail "Git이 설치되어 있지 않습니다."
command -v systemctl >/dev/null || fail "systemctl 명령을 찾지 못했습니다."

step 1 "GitHub main 브랜치 최신 코드 가져오기"
git pull --ff-only origin main || fail "git pull 실패: 로컬 수정·충돌·네트워크를 확인하세요."

step 2 "프로젝트 Python 가상환경 확인"
PYTHON="$PROJECT_ROOT/.venv/bin/python"
if [[ ! -x "$PYTHON" ]]; then
    command -v python3 >/dev/null || fail "python3가 없습니다."
    python3 -m venv .venv || fail ".venv 생성 실패: python3-venv 패키지 확인 필요"
    echo "Python 가상환경을 새로 생성했습니다."
fi
"$PYTHON" --version

step 3 "필요한 라이브러리 설치"
"$PYTHON" -m pip install -r requirements.txt || fail "패키지 설치 실패. 네트워크·의존성 충돌 확인 필요."

step 4 "Python 구문 및 파일 확인"
"$PYTHON" -m compileall -q app.py document_api.py document_pipeline.py rag_search.py local_status.py vlm_ocr.py settings.py llm_providers.py chat_search.py ||
    fail "Python 구문 오류가 있습니다. 서버를 재시작하지 않습니다."
[[ -f static/documents.html ]] || fail "static/documents.html이 없습니다."

step 5 "문서 처리 오프라인 단위 테스트"
"$PYTHON" -m unittest discover -s tests -p 'test_*.py' -v ||
    fail "단위 테스트 실패. 서버는 기존 상태로 유지합니다."

step 6 "FastAPI 사용자 서비스 재시작"
if ! systemctl --user cat langchain-lab.service >/dev/null 2>&1; then
    echo "서비스가 등록되지 않아 최초 설정을 진행합니다."
    bash scripts/install-service.sh ||
        fail "systemd 서비스 등록 실패"
fi
systemctl --user restart langchain-lab.service ||
    fail "서비스 재시작 실패. journalctl --user -u langchain-lab -n 40 확인 필요"

step 7 "실행 상태 및 문서 관리 API 확인"
sleep 2
systemctl --user is-active --quiet langchain-lab.service ||
    fail "서비스가 active가 아닙니다. journalctl --user -u langchain-lab -n 40 --no-pager"
"$PYTHON" - <<'PY'
import json
import sys
import time
from urllib.request import urlopen

base = "http://127.0.0.1:8000"
last_error = "응답 없음"
for _ in range(12):
    try:
        with urlopen(base + "/openapi.json", timeout=3) as r:
            paths = json.load(r)["paths"]
        if "/api/documents/upload" not in paths:
            raise RuntimeError("새 문서 API가 없는 구버전 프로세스가 포트 8000에서 실행 중입니다.")
        with urlopen(base + "/api/documents", timeout=3) as r:
            result = json.load(r)
        if "documents" not in result:
            raise RuntimeError("문서 목록 API 응답 형식이 올바르지 않습니다.")
        print("FastAPI /documents 및 /api/documents 정상")
        print("등록 문서 수:", len(result["documents"]))
        # Service diagnosis is informational; missing ES/model should not hide a valid deployment.
        try:
            with urlopen(base + "/api/documents/health/status", timeout=25) as h:
                health = json.load(h)
            es = health.get("elasticsearch", {})
            em = health.get("embedding", {})
            print("Elasticsearch:", "정상" if es.get("ok") else es.get("code", "미확인"))
            print("Qwen3 임베딩:", "정상" if em.get("ok") else em.get("code", "미확인"))
            if not es.get("ok") or not em.get("ok"):
                print("안내: 문서 관리 화면의 '연결 진단 실행'에서 해결 방법을 확인하세요.")
        except Exception:
            print("안내: 실시간 연결 진단은 완료되지 않았습니다. 문서 관리 화면에서 확인하세요.")
        break
    except (OSError, ValueError, KeyError, RuntimeError) as exc:
        last_error = str(exc)
        time.sleep(1)
else:
    sys.exit("로컬 서버 경로 검증 실패: " + last_error)
PY

printf '\n[완료] LangChain Lab 업데이트·검증·서비스 재시작 성공\n'
printf '문서 업로드: http://127.0.0.1:8000/documents\n'
printf '채팅 화면:   http://127.0.0.1:8000/\n'
printf '오류 로그:   journalctl --user -u langchain-lab -n 40 --no-pager\n'
