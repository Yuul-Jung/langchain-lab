"""Verify LM Studio Qwen3 embeddings with Elasticsearch 9.x kNN search.

This test only creates/updates documents in its dedicated lab index.
No credentials are saved or sent to GitHub.
"""
import getpass
import os
from pathlib import Path

import requests
from elasticsearch import Elasticsearch

ES_URL = os.getenv("ES_URL", "https://localhost:9200")
CA_CERT = os.path.expanduser(
    os.getenv("ES_CA_CERT", "~/.config/elasticsearch/http_ca.crt")
)
ES_USER = os.getenv("ES_USER", "elastic")
INDEX = "langchain_embedding_lab"
LM_URL = "http://127.0.0.1:1234/v1/embeddings"
MODEL = "text-embedding-qwen3-embedding-4b"
DOCUMENTS = [
    ("motor_hot", "전동기가 과열되면 온도 센서와 냉각팬을 점검한다."),
    ("motor_temp", "모터 온도가 높아질 때 보호 회로가 동작한다."),
    ("weather", "오늘 날씨는 맑고 바람이 약하다."),
]
QUERY = "모터 과열 시 확인할 사항은?"


def embed(text: str) -> list[float]:
    response = requests.post(
        LM_URL,
        json={"model": MODEL, "input": text},
        timeout=180,
    )
    response.raise_for_status()
    data = response.json()
    vector = data["data"][0]["embedding"]
    return vector


def main():
    if not Path(CA_CERT).is_file():
        raise SystemExit(f"CA 인증서가 없습니다: {CA_CERT}")

    password = os.environ.get("ES_PASSWORD") or getpass.getpass(
        f"Elasticsearch {ES_USER} 비밀번호: "
    )
    es = Elasticsearch(
        ES_URL, ca_certs=CA_CERT,
        basic_auth=(ES_USER, password), request_timeout=30
    )

    info = es.info()
    print("Elasticsearch:", info["version"]["number"])

    query_vector = embed(QUERY)
    dimension = len(query_vector)
    print("임베딩 차원:", dimension)
    if dimension != 2560:
        raise SystemExit(f"예상과 다른 벡터 차원: {dimension}")

    # Protect any pre-existing index with this name.
    if es.indices.exists(index=INDEX):
        mapping = es.indices.get_mapping(index=INDEX)
        props = mapping[INDEX]["mappings"]["properties"]
        field = props.get("embedding", {})
        if field.get("type") != "dense_vector" or field.get("dims") != dimension:
            raise SystemExit("기존 실습 인덱스 매핑이 다릅니다. 변경하지 않고 종료합니다.")
    else:
        es.indices.create(
            index=INDEX,
            mappings={"properties": {
                "text": {"type": "text"},
                "embedding": {
                    "type": "dense_vector",
                    "dims": dimension,
                    "index": True,
                    "similarity": "cosine",
                },
            }},
        )
        print("실습 인덱스 생성:", INDEX)

    # Deterministic IDs let us rerun without duplicates.
    for doc_id, text in DOCUMENTS:
        vector = embed(text)
        if len(vector) != dimension:
            raise SystemExit("문서와 질문의 임베딩 차원이 다릅니다.")
        es.index(
            index=INDEX, id=doc_id,
            document={"text": text, "embedding": vector},
        )
    es.indices.refresh(index=INDEX)

    result = es.search(
        index=INDEX, size=3,
        knn={
            "field": "embedding",
            "query_vector": query_vector,
            "k": 3,
            "num_candidates": 10,
        },
        body={"_source": ["text"]},
    )
    print("\n질문:", QUERY)
    for rank, hit in enumerate(result["hits"]["hits"], 1):
        print(f"{rank}. 점수 {hit['_score']:.4f} | {hit['_source']['text']}")
    print("\n벡터 저장 및 검색 요청 완료")


if __name__ == "__main__":
    main()
