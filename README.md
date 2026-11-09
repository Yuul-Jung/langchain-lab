# LangChain Lab — 로컬 AI/RAG 웹 서비스

LM Studio + DeepSeek 14B + Qwen3 임베딩 4B + Elasticsearch 9.x + FastAPI/LangChain.

## 접속 구조

- **실행 주소:** http://127.0.0.1:8000
- GitHub: 소스코드 업데이트 및 버전 관리
- FastAPI가 HTML과 API를 **같은 출처**에서 제공하므로 GitHub Pages ↔ 로컬 API의 CORS 문제를 피합니다.
- GitHub Pages는 Python 서버가 아니며, 루트 공개 페이지는 별도 정적 실습용으로 남겨 둡니다.
- 외부 공개 서버가 아닙니다. 현재 PC에서만 사용할 수 있습니다.

## Ubuntu 최초 설정 (한 번만)

LM Studio에서 Local Server를 시작하고 DeepSeek와 Qwen3-Embedding 모델을 사용할 수 있도록 설정합니다.

```bash
cd ~/langchain_web
git pull origin main
source .venv/bin/activate
python -m pip install -r requirements.txt
python scripts/configure-elasticsearch.py
bash scripts/install-service.sh
```

`configure-elasticsearch.py`는 한 번만 실행하여 비밀번호를 입력합니다. `.env`는 GitHub에 업로드되지 않으며, 권한 `600`으로 생성됩니다.

기존 터미널에서 `uvicorn`을 수동 실행 중이라면 **그 터미널에서 Ctrl+C로 중지**합니다. 이후:

```bash
systemctl --user start langchain-lab
systemctl --user status langchain-lab --no-pager
curl http://127.0.0.1:8000/api/models
```

로그 확인: `journalctl --user -u langchain-lab -n 40 --no-pager`

**서비스는 사용자 세션에 로그인할 때 자동 시작됩니다.** 우분투 로그인 전에도 실행해야 한다면 `loginctl enable-linger` 등 별도 설정 및 보안 검토가 필요합니다. 우선 불필요한 변경을 피합니다.

## LM Studio 자동 실행

GUI를 이미 설치해 사용 중이므로 LM Studio의 설정(`Ctrl+,`)에서 **Run LLM server on login**을 활성화합니다. 기존 서버 상태 자동 복원 기능을 사용합니다. 헤드리스 별도 `llmster` 설치는 지금 필요하지 않습니다.

- 공식 안내: https://lmstudio.ai/docs/developer/core/headless
- 터미널 확인: `lms server status`
- 수동 시작(필요시): `lms server start`

## 사용

브라우저에서 http://127.0.0.1:8000 접속 → `일반 채팅` 또는 `RAG 문서 검색` 선택.

RAG는 **기존** `langchain_embedding_lab` 인덱스를 읽기 전용으로 검색합니다. 새 문서 업로드/인덱스 수정 기능은 아직 없습니다. RAG 검색 결과의 출처와 점수는 화면에 표시됩니다.

## 주의

- LM Studio와 FastAPI는 `127.0.0.1`에만 바인딩하세요.
- 관리자 `elastic` 계정은 초기 실습용입니다. 향후 서비스 계정에 최소 권한을 부여하세요.
- `.env`, 비밀번호, 가상환경, 기술 문서나 대화 로그를 공개 저장소에 넣지 마세요.
- 모델이 메모리에 실제 로드되거나 JIT 로딩 가능한 상태여야 RAG 동작이 가능합니다.
- 현재 저장된 대화는 새로고침하면 사라집니다.
