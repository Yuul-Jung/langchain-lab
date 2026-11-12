# LangChain Lab — 로컬 AI/RAG 웹 서비스

LM Studio + DeepSeek 14B + Qwen3 임베딩 4B + Elasticsearch 9.x + FastAPI/LangChain.

## 접속 구조

- **실행 주소:** http://127.0.0.1:8000
- GitHub: 소스코드 업데이트 및 버전 관리
- FastAPI가 HTML과 API를 **같은 출처**에서 제공하므로 GitHub Pages ↔ 로컬 API의 CORS 문제를 피합니다.
- GitHub Pages는 Python 서버가 아니며, 루트 공개 페이지는 별도 정적 실습용으로 남겨 둡니다.
- 외부 공개 서버가 아닙니다. 현재 PC에서만 사용할 수 있습니다.

## GitHub Pages 첫 화면 → 로컬 실행 게이트 (2026-11)

공개 시작 페이지: https://yuul-jung.github.io/langchain-lab/

**실행 순서**

1. 공개 시작 페이지에서 **최초 설정/업데이트** 명령을 복사해 Ubuntu 터미널에서 실행합니다. 기존 프로젝트는 `bash ~/langchain_web/scripts/update-local.sh`를 사용합니다.
2. 이후 평소에는 `bash ~/langchain_web/scripts/start-local.sh`만 실행합니다. 이 스크립트는 기존 FastAPI 사용자 서비스를 필요할 때 시작하고, LM Studio가 닫혀 있으면 `lms server start`를 시도하며 Elasticsearch 연결 상태를 검사합니다.
3. 로컬 채팅은 http://127.0.0.1:8000/ , 문서 관리자는 http://127.0.0.1:8000/documents 에서 실행합니다.

공개 GitHub Pages는 브라우저 보안상 로컬 Ubuntu 명령을 직접 실행할 수 없습니다. 시작 페이지에는 **명령 복사**와 로컬 서비스로 이동하는 링크만 제공합니다. 브라우저에서 로컬 상태 검사는 동일 출처 API가 아닌 경우 차단될 수 있으므로 **진단 결과는 로컬 서버나 터미널에서 확인**합니다.

- `start-local.sh`는 패키지를 재설치하거나 데이터·인덱스·비밀번호를 변경하지 않습니다.
- Elasticsearch는 권한이 필요한 시스템 서비스이므로 `start-local.sh`가 자동으로 `sudo`를 실행하지 않습니다. 중단 상태라면 사용자 확인 후 `sudo systemctl start elasticsearch`를 별도 실행합니다.
- LM Studio 실행 성공과 DeepSeek/Qwen3 모델 로드 성공은 별개입니다. 실제 임베딩 정상 여부는 로컬 진단 API로 확인합니다.
- 사용자 개인 PC가 아닌 다른 컴퓨터에서 GitHub Pages를 열어도 `127.0.0.1`은 **그 컴퓨터 자체**를 의미합니다.

## 단계별 품질 검증 — 우선 개선 축

검색 엔진이나 프레임워크를 추가하기 전에 **PDF 전처리 → 임베딩 → 검색 → 답변 생성** 네 단계를 별도 평가합니다.

```bash
# 최신 읽기 전용 진단 스크립트 받기
cd ~/langchain_web && git pull --ff-only origin main

# 1. 문서별 PDF 추출·청크·색인 결과 요약
.venv/bin/python scripts/evaluate-pipeline.py

# 2. 임베딩 서버와 Elasticsearch를 실제 사용한 검색 검사
.venv/bin/python scripts/evaluate-pipeline.py --query "UART 16배 오버샘플링"

# 3. 해당 키워드가 검색 결과 본문에 들어 있는지 추가 확인
.venv/bin/python scripts/evaluate-pipeline.py --query "UART 수신" --expected "UART"
```

- **전처리:** 추출 문자 수, 절/청크 수, 페이지형 제목 수, 제목 추정 수, 공백 청크를 검사합니다. 읽기 전용이며 원본이나 인덱스를 수정하지 않습니다.
- **임베딩:** 실제 검색에 사용할 임베딩 모델과 벡터 차원 확인은 기존 `/api/documents/health/status`에서 수행합니다.
- **검색:** 결과 개수·점수·페이지·본문 문자 수만 출력합니다. 검색 결과의 실제 텍스트와 파일명은 출력하지 않습니다. `--expected`는 **키워드 포함 검사**일 뿐 의미 검색의 정확도를 증명하지 않습니다.
- **답변 생성:** 이 스크립트는 LLM을 호출하지 않습니다. 근거 문서와 정답이 확보된 평가 질문 세트를 만든 후 출처 일치성·사실 정확성·한글 출력 품질을 따로 평가합니다.
- **판정:** 색인 상태 `indexed`와 높은 유사도 점수만으로 시스템 전체 정확도를 합격 처리하지 않습니다.

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

## 문서 업로드 시 `failed` / 중복 업로드 진단

제2장 문서 원본과 구조화 정보는 로컬에 이미 저장되어 있을 수 있습니다. **같은 PDF를 다시 업로드할 필요가 없습니다.** 등록 상태가 `failed`라면 문서 관리 화면에서 다음 순서를 사용하세요.

1. `연결 진단 실행` → Elasticsearch와 Qwen3 임베딩 서버 상태 확인
2. 문서 목록에서 `구조 보기` → 기존 자료와 색인 실패 원인 확인
3. 설정 문제를 해결한 후 `벡터 등록 재시도` 클릭
4. 상태가 `indexed`로 전환되는지 확인한 뒤 문서 검색 실행

`/api/documents/health/status`는 비밀번호를 노출하지 않는 로컬 진단 API입니다. 기존 데이터(원본·분석 제안·검토 상태)는 그대로 유지됩니다.

현 버전의 PDF 구조 추출은 **페이지 단위**이며, `PDF 1쪽`은 실제 장 제목이 아닙니다. PDF의 진짜 장절·표·도면 구조 분석은 향후 별도 고도화할 예정입니다.

UI의 `undefined` 텍스트 출력 오류는 JavaScript 요소 생성 함수에서 `undefined`를 문자열로 출력하던 문제로 수정했습니다. GitHub 코드를 가져온 뒤 기존 로컬 서비스를 다시 시작해야 적용됩니다.

## ES_AUTH 인증 실패 복구 (기존 PDF 유지)

문서 관리자에서 `ES_AUTH`가 나타나면 Elasticsearch가 현재 프로젝트의 `.env` 비밀번호를 받아들이지 않은 것입니다. **서버의 비밀번호를 함부로 초기화하거나 문서를 삭제하지 마세요.**

```bash
# 최신 안전 복구 스크립트 받기
cd ~/langchain_web
git pull --ff-only origin main

# 비밀번호 입력 및 실제 Elasticsearch 인증 검증 후 .env만 갱신
.venv/bin/python scripts/repair-es-auth.py

# 재시작과 최종 확인
systemctl --user restart langchain-lab
curl -s http://127.0.0.1:8000/api/documents/health/status
```

비밀번호는 터미널에 표시되지 않습니다. 검증에 실패하면 기존 `.env`는 변경하지 않습니다. 기존 `uploads/` 원본과 `data/` 카탈로그, Elasticsearch 인덱스는 삭제하지 않습니다. 진단 결과에서 Elasticsearch와 임베딩이 모두 정상인 경우 기존 문서의 **구조 보기 → 벡터 등록 재시도**를 누릅니다.

스크립트는 사용자가 **현재 알고 있는 Elasticsearch 계정 비밀번호**를 입력받는 방식입니다. 비밀번호 자체를 잊은 경우에는 별도의 안전한 관리자 재설정 절차가 필요합니다.

## 인증 복구 후에도 ES_AUTH가 반복될 때

비밀번호 재설정과 `repair-es-auth.py` 성공 후에도 색인이 401로 실패할 수 있는 원인 중 하나는 프로세스에 남아 있는 예전 `ES_PASSWORD` 환경변수입니다. 이 프로젝트는 **`rag_search.py`에서 로컬 `.env`를 요청 시마다 다시 읽도록 수정**했으며, 환경변수와 값이 다를 경우 프로젝트의 `.env`를 우선 사용합니다.

```bash
# 단일 업데이트 스크립트가 소스·테스트·서비스를 순서대로 반영
bash ~/langchain_web/scripts/update-local.sh

# 권한·비밀번호를 노출하지 않는 현재 접속 진단
curl -s http://127.0.0.1:8000/api/documents/health/status
```

진단의 `elasticsearch.ok`와 `embedding.ok`가 모두 `true`인지 확인합니다. 연결 성공 후 `failed`인 과거 기록이 자동으로 바뀌는 것은 아니므로, **2청크 안내서부터 벡터 등록 재시도**하여 새 결과를 확인합니다. 계속 실패한다면 새로 표시된 실패 코드와 실패 단계를 기준으로 추가 원인을 진단합니다.

서비스 장애 확인: `journalctl --user -u langchain-lab -n 40 --no-pager` (인증 관련 민감 정보는 외부에 공유하지 않음).

## 연결은 정상인데 색인이 계속 실패하는 경우 — 단일 문서 진단

서버 연결 상태가 모두 정상인데도 `failed`가 유지된다면, 이전 실패 기록인지 실제 색인 단계 오류인지 구별해야 합니다. PDF를 다시 업로드하거나 비밀번호를 재설정하지 말고 다음 진단을 실행합니다.

```bash
cd ~/langchain_web && git pull --ff-only origin main && .venv/bin/python scripts/diagnose-reindex.py
```

이 스크립트는 문서 목록에서 **가장 청크 수가 작은 failed 문서 1개**만 재색인하고 성공 여부 또는 오류 코드·단계를 출력합니다. `ES_AUTH` 과거 기록은 실제 요청 결과와 구분됩니다. 다른 문서와 원본 파일은 변경하지 않습니다.


## PDF 검색은 성공하지만 장·절 구조가 페이지로만 나올 때

이 문제는 벡터 검색 실패가 아닙니다. 기존 PDF 구조 추출이 페이지 단위로만 저장되었던 제한입니다. 수정된 `document_pipeline.py`는 줄 단위로 분리된 명확한 번호형 제목을 **추정 후보**로 감지합니다. 이 제목 후보는 `rule_inferred`이며 원본 PDF에 검증된 구조 태그가 있다는 뜻이 아닙니다.

```bash
bash ~/langchain_web/scripts/update-local.sh
```

로컬 `/documents`의 `05 · 문서 구조와 분석 정보`에서 문서를 열고 **LLM 분류 재분석** 버튼을 사용합니다. 처리 후 **PDF 제목·절 구조 후보**가 원본 구조와 별도로 나타납니다. 분류가 `heuristic`인 경우 실제 LLM 분석이 성공했다는 의미가 아니며, **분석 근거** 필드에서 폴백 여부를 확인해야 합니다.

기존 PDF와 벡터 색인은 변경하지 않고, 새 분류·순서 제안은 `proposed`로 되돌립니다. 즉, 예전 `approved` 판정을 새 분석에 자동 승계하지 않습니다. 기존 색인 청크의 절 ID를 변경하는 마이그레이션은 아직 구현되지 않았습니다.

