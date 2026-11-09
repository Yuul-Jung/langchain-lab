"""Verify LangChain connection to an LM Studio model."""

import requests
from langchain_openai import ChatOpenAI

url = "http://127.0.0.1:1234/v1"
models = requests.get(f"{url}/models", timeout=10).json()["data"]
if not models:
    raise RuntimeError("LM Studio에서 사용 가능한 모델을 찾지 못했습니다.")
model_id = models[0]["id"]

print("사용 모델:", model_id)
llm = ChatOpenAI(
    model=model_id,
    base_url=url,
    api_key="lm-studio",
    temperature=0,
    use_responses_api=False,
)
response = llm.invoke([
    ("system", "모든 최종 답변은 한국어로 작성하세요."),
    ("human", "LangChain이 무엇인지 간단하게 설명해줘."),
])
print(response.content)
