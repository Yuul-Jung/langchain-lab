"""Read-only Elasticsearch retrieval for local LangChain RAG.

Credentials are read from the local environment or an ignored .env file.
Never expose Elasticsearch credentials in a browser response.
"""
import base64
import os
from pathlib import Path

import requests
from dotenv import dotenv_values
from elasticsearch import Elasticsearch

ENV_FILE = Path(__file__).resolve().parent / ".env"

# The local .env is the canonical credential source for this single-user service.
# An inherited ES_PASSWORD from a desktop/systemd session must not silently
# override a password that repair-es-auth.py has just verified and saved.
def es_settings():
    values = dotenv_values(ENV_FILE) if ENV_FILE.is_file() else {}
    def setting(name, default):
        return values.get(name) or os.environ.get(name) or default

    return {
        "url": setting("ES_URL", "https://localhost:9200"),
        "ca_cert": os.path.expanduser(
            setting("ES_CA_CERT", "~/.config/elasticsearch/http_ca.crt")
        ),
        "user": setting("ES_USER", "elastic"),
        "password": setting("ES_PASSWORD", ""),
    }


INDEX = os.getenv("ES_RAG_INDEX", "langchain_embedding_lab")
EMBEDDING_MODEL = "text-embedding-qwen3-embedding-4b"
LM_STUDIO_URL = os.getenv("LM_STUDIO_URL", "http://127.0.0.1:1234/v1")


def es_client():
    settings = es_settings()
    if not settings["password"]:
        raise RuntimeError("ES_PASSWORD가 설정되지 않았습니다.")
    if not Path(settings["ca_cert"]).is_file():
        raise RuntimeError("Elasticsearch CA 인증서를 찾지 못했습니다.")
    # UTF-8 Basic auth supports non-ASCII passwords.
    raw = f'{settings["user"]}:{settings["password"]}'.encode("utf-8")
    header = "Basic " + base64.b64encode(raw).decode("ascii")
    return Elasticsearch(
        settings["url"], ca_certs=settings["ca_cert"],
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
