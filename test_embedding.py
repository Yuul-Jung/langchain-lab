"""Test Qwen3 embedding generation through the local LM Studio API."""

import requests

BASE_URL = "http://127.0.0.1:1234/v1"
MODEL_ID = "text-embedding-qwen3-embedding-4b"

def main():
    # Request one vector for a Korean engineering sentence.
    response = requests.post(
        f"{BASE_URL}/embeddings",
        json={"model": MODEL_ID, "input": "전동기 과열 방지 시스템"},
        timeout=120,
    )
    response.raise_for_status()
    data = response.json()
    vector = data["data"][0]["embedding"]
    print("모델:", MODEL_ID)
    print("임베딩 생성 성공")
    print("벡터 차원:", len(vector))
    print("벡터 일부:", vector[:5])

if __name__ == "__main__":
    main()
