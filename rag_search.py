"""Read-only Elasticsearch retrieval for local LangChain RAG.

Credentials are read from the local environment or an ignored .env file.
Never expose Elasticsearch credentials in a browser response.
"""
import base64
import os
from pathlib import Path

import requests
from dotenv import load_dotenv
from elasticsearch import Elasticsearch

load_dotenv(Path(__file__).resolve().parent / ".env")

INDEX = os.getenv("ES_RAG_INDEX", "langchain_embedding_lab")
ES_URL = os.getenv("ES_URL", "https://localhost:9200")
ES_CA_CERT = os.path.expanduser(
    os.getenv("ES_CA_CERT", "~/.config/elasticsearch/http_ca.crt")
)
ES_USER = os.getenv("ES_USER", "elastic")
EMBEDDING_MODEL = "text-embedding-qwen3-embedding-4b"
LM_STUDIO_URL = os.getenv("LM_STUDIO_URL", "http://127.0.0.1:1234/v1")


def es_client():
    password = os.getenv("ES_PASSWORD", "")
    if not password:
        raise RuntimeError("ES_PASSWORD가 설정되지 않았습니다.")
    if not Path(ES_CA_CERT).is_file():
        raise RuntimeError("Elasticsearch CA 인증서를 찾지 못했습니다.")
    # Support UTF-8 passwords used by Elasticsearch basic authentication.
    raw = f"{ES_USER}:{password}".encode("utf-8")
    header = "Basic " + base64.b64encode(raw).decode("ascii")
    return Elasticsearch(
        ES_URL, ca_certs=ES_CA_CERT,
        headers={"Authorization": header}, request_timeout=20,
    )


def embed_query(query: str):
    response = requests.post(
        f"{LM_STUDIO_URL}/embeddings",
        json={"model": EMBEDDING_MODEL, "input": query}, timeout=120,
    )
    response.raise_for_status()
    vector = response.json()["data"][0]["embedding"]
    if len(vector) != 2560:
        raise RuntimeError("임베딩 벡터 차원이 2560이 아닙니다.")
    return vector


def search_documents(query: str, limit: int = 3):
    """Search existing documents only; do not create or change the index."""
    es = es_client()
    if not es.indices.exists(index=INDEX):
        raise RuntimeError(f"RAG 인덱스가 없습니다: {INDEX}")

    mapping = es.indices.get_mapping(index=INDEX)
    properties = mapping[INDEX]["mappings"].get("properties", {})
    field = properties.get("embedding", {})
    if field.get("type") != "dense_vector" or field.get("dims") != 2560:
        raise RuntimeError("인덱스의 임베딩 매핑이 호환되지 않습니다.")

    vector = embed_query(query)
    result = es.search(
        index=INDEX, size=limit,
        knn={
            "field": "embedding", "query_vector": vector,
            "k": limit, "num_candidates": max(10, limit),
        },
        source=["text"],
    )
    return [
        {
            "id": hit["_id"],
            "score": round(hit["_score"], 4),
            "text": hit["_source"].get("text", ""),
        }
        for hit in result["hits"]["hits"]
    ]
