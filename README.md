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

일반 RAG 채팅은 **기존** `langchain_embedding_lab` 인덱스를 읽기 전용으로 검색합니다. 제2장 문서 업로드 기능은 별도 인덱스 `langchain_documents_v1`에 등록하며, 두 검색 경로는 아직 분리되어 있습니다. RAG 채팅에서 새 업로드 문서를 자동 검색하도록 전환하는 기능은 후속 통합 과제입니다.

## 주의

- LM Studio와 FastAPI는 `127.0.0.1`에만 바인딩하세요.
- 관리자 `elastic` 계정은 초기 실습용입니다. 향후 서비스 계정에 최소 권한을 부여하세요.
- `.env`, 비밀번호, 가상환경, 기술 문서나 대화 로그를 공개 저장소에 넣지 마세요.
- 모델이 메모리에 실제 로드되거나 JIT 로딩 가능한 상태여야 RAG 동작이 가능합니다.
- 현재 저장된 대화는 새로고침하면 사라집니다.

## 학습용 HTML 교재

- [전체 구축 과정·블록다이어그램·검증 및 문제 해결](docs/learning-guide.html)
- GitHub Pages 배포 링크: https://yuul-jung.github.io/langchain-lab/docs/learning-guide.html

교재는 실제 성공 단계와 검증 대기 단계를 구별하여 정리했습니다.

## 교육용 블록다이어그램 표준 템플릿

- [표준 스타일 가이드 + 구조도 6종](docs/diagram-style-guide.html)
- [공통 CSS 디자인 토큰](docs/diagram-components.css)
- [기존 LangChain 구축 학습 교재](docs/learning-guide.html)

GitHub Pages: https://yuul-jung.github.io/langchain-lab/docs/diagram-style-guide.html

구조도는 HTML/CSS로 작성되어 텍스트와 박스를 수정할 수 있으며, 인쇄/PDF 저장도 지원합니다.


## 제2장 — 로컬 문서 업로드·구조화 (v2.0 학습 과정)

- [제2장 HTML 학습안내서](docs/ch02-document-ingestion.html)
- [제1장 HTML 학습안내서](docs/learning-guide-detailed.html)
- 로컬 웹 문서 관리자: http://127.0.0.1:8000/documents
- API: `/api/documents`, `/api/documents/upload`, `/api/documents/search`, `/api/documents/{document_id}/review`
- 처리 기능: PDF/DOCX/TXT/Markdown/HTML 구조 추출, 분류 제안, 원본·선수관계 분리, 추천 학습 순서, Elasticsearch 2,560차원 벡터 등록
- 문서 원본: `uploads/documents/` (Git 추적 제외), 카탈로그: `data/document_catalog/` (Git 추적 제외)
- 파일당 제한: 8MB, 최다 150개 절 및 160개 청크. 스캔 PDF OCR 미지원
- AI 분류 실패 시 키워드 기반 임시 분류. 제안은 `review_status=proposed`로 저장하며 원본 순서를 덮어쓰지 않음

### 제2장 코드 반영

```bash
# GitHub에서 최신 소스 받기
cd ~/langchain_web
git pull origin main

# Python 패키지 설치
source .venv/bin/activate
python -m pip install -r requirements.txt

# 외부 서버 없이 구문·구조·원본 순서·중복 검사 수행
python -m compileall -q app.py document_api.py document_pipeline.py
python -m unittest discover -s tests -p 'test_document_pipeline.py' -v

# 사용자 FastAPI 서비스 재시작
systemctl --user restart langchain-lab

# 브라우저로 문서 관리자 접속
# http://127.0.0.1:8000/documents
```

**검증 상태:** GitHub 소스와 오프라인 자동 테스트 코드를 추가했습니다. 실제 사용자의 LM Studio, Elasticsearch, 파일별 추출 및 브라우저 업로드 동작은 로컬 PC에서 실행·검증해야 합니다. CI 설정은 `.github/workflows/document-pipeline-tests.yml`에 있습니다.

**보안:** 로컬 개발 환경 전용입니다. `.env`와 업로드 원본은 Git에 추가하지 마세요. 외부 네트워크에 노출하지 마세요. 업로드를 통한 스크립트 실행을 허용하지 않지만, 불신 파일에 대한 완전한 악성 파일 검사나 멀티유저 인증은 구현되지 않았습니다.

## 한 번에 업데이트·검증·실행 (권장)

우분투의 **프로젝트 폴더가 이미 존재하는 경우**, 다음 명령 **한 줄**로 최신 소스 다운로드, Python 가상환경 확인, 필수 패키지 설치, 구문 및 오프라인 단위 테스트, FastAPI 서비스 재시작, /documents API 진단까지 처리합니다.

```bash
cd ~/langchain_web && git pull --ff-only origin main && bash scripts/update-local.sh
```

처음 한 번 위 명령으로 스크립트를 받아 실행한 이후에는 다음 명령만 사용합니다.

```bash
bash ~/langchain_web/scripts/update-local.sh
```

선택적으로 우분투 바탕화면에 **LangChain Lab 업데이트** 실행 아이콘을 만들 수 있습니다.

```bash
bash ~/langchain_web/scripts/install-update-shortcut.sh
```

- 업데이트 스크립트는 `scripts/update-local.sh`입니다.
- GitHub Pages에서 로컬 Ubuntu 명령을 직접 실행할 수는 없습니다. 업데이트는 로컬 터미널 또는 바탕화면 실행 아이콘에서 시작합니다.
- `git pull --ff-only`는 로컬 변경을 자동 병합하지 않고 문제가 있을 때 멈춥니다.
- 설치 또는 검증 실패 시 **기존 서버를 재시작하지 않고** 오류를 표시합니다. 서비스 설정이 없는 최초 환경에서는 등록합니다.
- 자동 검사 통과가 실제 Elasticsearch 임베딩 연동의 성공을 보장하지 않으므로, 문서 하나를 업로드하여 확인해야 합니다.
- 새 문서 API 확인: http://127.0.0.1:8000/documents
