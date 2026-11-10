#!/usr/bin/env python3
"""Non-destructive one-document indexing diagnostic for a local LangChain Lab.

This script uses the existing FastAPI endpoints: it never deletes documents,
never resets credentials, never creates a new upload, and does not print secrets.
It chooses the smallest failed document to minimize model inference work.
"""
import json
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BASE = "http://127.0.0.1:8000"


def request(path, method="GET", timeout=180):
    req = Request(BASE + path, method=method)
    try:
        with urlopen(req, timeout=timeout) as response:
            return response.status, json.load(response)
    except HTTPError as exc:
        try:
            payload = json.load(exc)
        except (ValueError, UnicodeError):
            payload = {}
        return exc.code, payload


def fail(message):
    print("[진단 중단]", message)
    sys.exit(1)


def detail(payload):
    value = payload.get("detail", {}) if isinstance(payload, dict) else {}
    if isinstance(value, str):
        return {"message": value}
    if isinstance(value, dict):
        return {key: value.get(key, "") for key in ("code", "phase", "hint", "message")}
    return {"message": "상세 오류를 반환하지 않았습니다."}


def main():
    print("[1/4] 로컬 서비스 현재 연결 상태")
    try:
        status, health = request("/api/documents/health/status", timeout=35)
    except (URLError, TimeoutError, OSError) as exc:
        fail("FastAPI 8000 포트에 연결하지 못했습니다. systemctl --user status langchain-lab 확인")
    if status != 200:
        fail("문서 진단 API가 동작하지 않습니다. 업데이트 후 서비스를 재시작하세요.")

    for key, label in (("elasticsearch", "Elasticsearch"), ("embedding", "Qwen3 임베딩")):
        item = health.get(key, {})
        print(" ", label, ":", "정상" if item.get("ok") else item.get("code", "오류"))
        if not item.get("ok"):
            print("  안내:", item.get("hint", "해당 서버 설정을 확인하세요."))
    if not health.get("elasticsearch", {}).get("ok") or not health.get("embedding", {}).get("ok"):
        fail("연결 진단이 완료되지 않아 색인을 수행하지 않았습니다.")

    print("[2/4] 기존 문서의 저장·색인 상태")
    status, payload = request("/api/documents")
    if status != 200:
        fail("문서 목록 조회에 실패했습니다.")
    documents = payload.get("documents", [])
    print(" 등록된 문서:", len(documents))
    for item in documents:
        label = item.get("filename", "이름 없음")
        print("  -", label, "|", item.get("index_status", "미확인"),
              "| 청크", item.get("chunk_count", "?"))

    targets = [d for d in documents if d.get("index_status") == "failed"]
    if not targets:
        print("재색인 대상 failed 문서가 없습니다.")
        return
    target = min(targets, key=lambda item: item.get("chunk_count") or 999999)
    document_id = target.get("document_id")
    if not document_id or len(document_id) != 32:
        fail("대상 문서 ID가 유효하지 않습니다.")
    print("[3/4] 최소 청크 문서 1개만 재색인")
    print(" 대상:", target.get("filename"), "| 청크", target.get("chunk_count"))
    print(" 기존 원본·분류·순서와 다른 문서는 건드리지 않습니다.")
    try:
        status, result = request(f"/api/documents/{document_id}/reindex",
                                 method="POST", timeout=240)
    except (URLError, TimeoutError, OSError):
        fail("색인 요청 시간 초과 또는 연결 끊김. 서버 로그를 확인하세요.")

    print("[4/4] 재색인 결과")
    if status == 200:
        print(" 결과: indexed")
        print(" 등록 청크:", result.get("chunk_count"))
        print(" 문서 검색 화면에서 관련 질의를 입력하여 검색 결과를 확인하세요.")
        return

    print(" 결과: 실패 | HTTP", status)
    issue = detail(result)
    for k, value in issue.items():
        if value:
            print(" ", k, ":", value)
    print("같은 PDF를 재업로드하거나 Elasticsearch 비밀번호를 다시 재설정하지 마세요.")
    print("위의 오류 코드·단계를 확인하면 다음 조치를 결정할 수 있습니다.")
    sys.exit(2)


if __name__ == "__main__":
    main()
