"""Save an Elasticsearch password privately into the project's ignored .env file."""
from getpass import getpass
from pathlib import Path
import os

ROOT = Path(__file__).resolve().parents[1]
path = ROOT / ".env"
if path.exists():
    print("기존 .env 파일을 보존합니다. 필요하면 직접 수정하세요.")
    raise SystemExit(0)

password = getpass("Elasticsearch 비밀번호 (화면에 표시되지 않음): ")
if not password:
    raise SystemExit("빈 비밀번호이므로 저장하지 않았습니다.")
# Reject line breaks, which could corrupt dotenv syntax.
if "\n" in password or "\r" in password:
    raise SystemExit("줄바꿈이 포함된 비밀번호는 지원하지 않습니다.")
# Quoted dotenv value, escaping backslashes and double quotes.
escaped = password.replace("\\", "\\\\").replace('"', '\\"')
fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, "w", encoding="utf-8") as stream:
    stream.write('ES_USER=elastic\n')
    stream.write('ES_URL=https://localhost:9200\n')
    stream.write('ES_CA_CERT=~/.config/elasticsearch/http_ca.crt\n')
    stream.write('ES_PASSWORD="' + escaped + '"\n')
print("사용자 전용 .env 저장 완료 (Git 추적 제외).")
