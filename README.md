# LangChain Lab

LM Studio의 로컬 LLM을 LangChain 및 FastAPI와 연결하는 브라우저 기반 채팅 실습입니다.

## 구성

- `app.py`: FastAPI 및 LangChain 서버
- `static/index.html`: 한국어 채팅 화면
- `requirements.txt`: Python 의존성
- `test_langchain.py`: 로컬 모델 연결 검증 예제
- `.gitignore`: 가상환경 및 비밀 파일 제외

## Ubuntu 실행

LM Studio에서 모델을 로드하고 **Local Server**를 시작합니다. 기본 주소: `http://127.0.0.1:1234/v1`.

```bash
git clone https://github.com/Yuul-Jung/langchain-lab.git
cd langchain-lab
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m uvicorn app:app --host 127.0.0.1 --port 8000 --reload
```

브라우저에서 **http://127.0.0.1:8000** 접속.

> GitHub Pages에서는 Python 서버나 LM Studio 모델을 실행할 수 없습니다. 이 저장소는 소스 배포용이고, 채팅 기능은 로컬 FastAPI 서버에서 동작합니다.

## 보안과 제한

- 서버는 기본적으로 PC 자체(127.0.0.1)에서만 접속하도록 실행합니다.
- 공개 인터넷에 LM Studio 포트(1234)나 인증 없는 FastAPI 서버를 그대로 노출하지 마세요.
- `.venv/`, `.env`, 토큰, 개인 문서 및 대화 로그를 GitHub에 업로드하지 마세요.
- 현재 버전은 브라우저 메모리에만 대화를 보관하며 새로고침 시 초기화됩니다.
- 다중 사용자 인증, 영구 대화 저장, 실시간 스트리밍, RAG는 이후 단계에서 구현합니다.
