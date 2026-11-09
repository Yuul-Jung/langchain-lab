"""Local browser chat using LangChain and LM Studio."""

import os
from pathlib import Path

import requests
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

BASE_DIR = Path(__file__).resolve().parent
LM_STUDIO_URL = os.getenv("LM_STUDIO_URL", "http://127.0.0.1:1234/v1")
app = FastAPI(title="LangChain Local AI Chat")

SYSTEM_PROMPT = (
    "당신은 한국어 AI 도우미입니다. "
    "최종 답변은 항상 한국어로 작성하고, 기술 용어는 필요한 경우 영어를 병기하세요."
)


class Message(BaseModel):
    role: str
    content: str = Field(min_length=1, max_length=20000)


class ChatRequest(BaseModel):
    messages: list[Message] = Field(min_length=1, max_length=20)


def available_models() -> list[str]:
    """Read model IDs from the local LM Studio server."""
    try:
        response = requests.get(f"{LM_STUDIO_URL}/models", timeout=10)
        response.raise_for_status()
        return [item["id"] for item in response.json().get("data", [])]
    except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
        raise HTTPException(
            status_code=503, detail="LM Studio 서버에 연결할 수 없습니다."
        ) from exc


@app.get("/")
def index():
    """Serve the local chat user interface."""
    return FileResponse(BASE_DIR / "static" / "index.html")


@app.get("/api/models")
def get_models():
    """Return the available local models."""
    return {"models": available_models()}


@app.post("/api/chat")
def chat(request: ChatRequest):
    """Send conversation messages to LM Studio through LangChain."""
    models = available_models()
    if not models:
        raise HTTPException(status_code=503, detail="로드된 모델이 없습니다.")

    # Keep untrusted client messages out of the system role.
    messages = [("system", SYSTEM_PROMPT)]
    for item in request.messages:
        if item.role not in ("user", "assistant"):
            raise HTTPException(status_code=400, detail="잘못된 메시지 역할입니다.")
        messages.append(
            ("human" if item.role == "user" else "ai", item.content)
        )

    # This initial version uses the first model listed by LM Studio.
    model_id = models[0]
    llm = ChatOpenAI(
        model=model_id,
        base_url=LM_STUDIO_URL,
        api_key="lm-studio",
        temperature=0,
        timeout=120,
        use_responses_api=False,
    )
    try:
        response = llm.invoke(messages)
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail="모델 응답에 실패했습니다. LM Studio 모델 로딩 상태를 확인하세요.",
        ) from exc

    answer = response.content
    if not isinstance(answer, str):
        answer = str(answer)
    return {"model": model_id, "answer": answer}
