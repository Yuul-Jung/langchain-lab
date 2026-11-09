#!/usr/bin/env bash
# Install the local FastAPI app as a per-user systemd service.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UNIT_DIR="${HOME}/.config/systemd/user"
UNIT_FILE="${UNIT_DIR}/langchain-lab.service"
PYTHON="${ROOT}/.venv/bin/python"
if [[ ! -x "$PYTHON" ]]; then
  echo "가상환경이 없습니다: $PYTHON"
  echo "python3 -m venv .venv && .venv/bin/python -m pip install -r requirements.txt"
  exit 1
fi
mkdir -p "$UNIT_DIR"
cat > "$UNIT_FILE" <<EOF
[Unit]
Description=LangChain Lab local FastAPI and RAG server
After=default.target

[Service]
Type=simple
WorkingDirectory=$ROOT
ExecStart=$PYTHON -m uvicorn app:app --host 127.0.0.1 --port 8000
Restart=on-failure
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=default.target
EOF
systemctl --user daemon-reload
systemctl --user enable langchain-lab.service
echo "자동 시작 등록 완료: $UNIT_FILE"
echo "중요: 기존 수동 uvicorn 서버가 8000 포트를 점유 중이면 그 터미널에서 Ctrl+C로 종료하세요."
echo "이후 시작: systemctl --user start langchain-lab"
echo "확인: systemctl --user status langchain-lab"
echo "로그: journalctl --user -u langchain-lab -n 40 --no-pager"
