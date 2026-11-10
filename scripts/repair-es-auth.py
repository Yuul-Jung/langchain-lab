#!/usr/bin/env python3
"""Repair ONLY the local .env Elasticsearch password after verifying login.

- Does not reset the Elasticsearch server password.
- Does not print, log or upload the password.
- Leaves the previous .env untouched if verification fails.
- Existing additional .env settings are preserved with python-dotenv set_key.
"""
import base64
import os
import stat
import sys
from getpass import getpass
from pathlib import Path

import requests
from dotenv import dotenv_values, set_key

ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT / ".env"


def main():
    if ENV_FILE.is_symlink():
        raise SystemExit("보안상 심볼릭 링크 .env 파일은 수정하지 않습니다.")
    if ENV_FILE.exists() and not ENV_FILE.is_file():
        raise SystemExit(".env가 일반 파일이 아닙니다.")

    values = dotenv_values(ENV_FILE) if ENV_FILE.exists() else {}
    user = values.get("ES_USER") or "elastic"
    url = (values.get("ES_URL") or "https://localhost:9200").rstrip("/")
    ca_path = Path(os.path.expanduser(
        values.get("ES_CA_CERT") or "~/.config/elasticsearch/http_ca.crt"
    ))
    if not url.startswith("https://"):
        raise SystemExit("HTTPS Elasticsearch 주소만 지원합니다.")
    if not ca_path.is_file():
        raise SystemExit("CA 인증서를 찾지 못했습니다. 기존 ES_CA_CERT 경로를 확인하세요.")

    print(f"연결 대상: {url} / 사용자: {user}")
    print("기존 .env의 기타 값과 업로드 문서는 변경하지 않습니다.")
    password = getpass("현재 Elasticsearch 로그인 비밀번호: ")
    if not password or "\n" in password or "\r" in password:
        raise SystemExit("비밀번호가 비어 있거나 줄바꿈을 포함합니다.")

    token = base64.b64encode(f"{user}:{password}".encode("utf-8")).decode("ascii")
    try:
        response = requests.get(
            url,
            headers={"Authorization": "Basic " + token},
            verify=str(ca_path), timeout=12,
        )
    except requests.RequestException:
        raise SystemExit("서버 접속 또는 인증서 검증 실패: .env를 변경하지 않았습니다.")
    if response.status_code != 200:
        print(f"Elasticsearch HTTP 상태: {response.status_code}")
        raise SystemExit("로그인 검증에 실패했습니다. .env를 변경하지 않았습니다.")
    try:
        info = response.json()
        if "version" not in info:
            raise ValueError("Unexpected response")
    except (ValueError, TypeError):
        raise SystemExit("Elasticsearch 서버 정보 확인 실패: .env를 변경하지 않았습니다.")

    if not ENV_FILE.exists():
        fd = os.open(str(ENV_FILE), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(f'ES_USER="{user}"\n')
            f.write(f'ES_URL="{url}"\n')
            f.write(f'ES_CA_CERT="{ca_path}"\n')
    else:
        os.chmod(ENV_FILE, stat.S_IRUSR | stat.S_IWUSR)

    set_key(str(ENV_FILE), "ES_PASSWORD", password, quote_mode="always")
    os.chmod(ENV_FILE, stat.S_IRUSR | stat.S_IWUSR)
    print("인증 성공. .env의 ES_PASSWORD만 갱신했습니다.")
    print("변경 사항을 적용하려면: systemctl --user restart langchain-lab")


if __name__ == "__main__":
    main()
