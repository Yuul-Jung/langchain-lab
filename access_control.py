"""(추가) 접근 제어: 기본은 이 PC 전용, 접속 비밀번호를 넣으면 다른 기기에서 로그인해 사용.

동작 요약 (2026-11-12)
- .env 에 ACCESS_PASSWORD 가 없으면: 이 PC(루프백)에서 온 요청만 받는다. 서버를 실수로 외부에
  열어도(--host 0.0.0.0) 다른 기기의 요청은 403 으로 거절한다.
- ACCESS_PASSWORD 가 있으면: 다른 기기는 /login 에서 비밀번호를 넣어 세션을 받아야 한다.
  이 PC 에서의 사용과 scripts/ 의 점검 명령은 로그인 없이 그대로 된다.
  (같은 PC 에 리버스 프록시를 두면 모든 요청이 루프백으로 보이므로 AUTH_REQUIRE_LOOPBACK=true 로 바꾼다.)
- 로그인 없이 믿는 루프백 요청은 Host 가 127.0.0.1·localhost(또는 ALLOWED_HOSTS)일 때만 받는다.
  악성 웹페이지가 자기 도메인을 127.0.0.1 로 바꿔 브라우저를 통해 접근하는 수법(DNS 리바인딩)을 막는다.
- 변경을 일으키는 요청(POST 등)은 보낸 페이지의 주소(Origin)가 이 서버의 주소와 같을 때만 받는다.
  다른 웹사이트가 내 브라우저를 통해 업로드·재추출 같은 요청을 보내는 수법(CSRF)을 막는다.
  curl 처럼 Origin 이 없는 요청은 브라우저가 아니므로 해당 없다.

세션은 서버에 저장하지 않는다. "만료시각.서명" 꼴의 값을 쿠키에 두고 HMAC 으로 검증한다.
이 모듈은 FastAPI 에 의존하지 않아 서버 없이 테스트한다.
"""
from __future__ import annotations

import hashlib
import hmac
import ipaddress
import time
from urllib.parse import urlsplit

SESSION_COOKIE = "lab_session"
# 로그인 자체에 필요한 경로는 항상 통과시킨다
OPEN_PATHS = frozenset({"/login", "/api/login", "/api/logout"})
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
# 서버의 상태를 바꿀 수 있는 요청 방식
UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def is_loopback(host: str | None) -> bool:
    """요청을 보낸 상대 주소가 이 PC 인지."""
    if not host:
        return False
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return host == "localhost"
    # 서버를 IPv6 로 열면 이 PC 의 IPv4 요청이 '::ffff:127.0.0.1' 꼴로 보인다
    mapped = getattr(address, "ipv4_mapped", None)
    return (mapped or address).is_loopback


def host_name(host_header: str | None) -> str:
    """Host 헤더에서 포트를 뗀 이름. '127.0.0.1:8000' → '127.0.0.1', '[::1]:8000' → '::1'."""
    value = (host_header or "").strip().lower()
    if value.startswith("["):
        return value[1:value.find("]")] if "]" in value else ""
    return value.rsplit(":", 1)[0] if value.count(":") == 1 else value


def make_token(secret: bytes, hours: float, now: float | None = None) -> str:
    expires = int((time.time() if now is None else now) + hours * 3600)
    signature = hmac.new(secret, str(expires).encode(), hashlib.sha256).hexdigest()
    return f"{expires}.{signature}"


def token_valid(token: str | None, secret: bytes, now: float | None = None) -> bool:
    """서명이 맞고 아직 만료되지 않았는지. 형식이 틀리면 False."""
    if not token or token.count(".") != 1:
        return False
    expires_text, signature = token.split(".")
    if not expires_text.isdigit():
        return False
    expected = hmac.new(secret, expires_text.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        return False
    return int(expires_text) > (time.time() if now is None else now)


def password_matches(given: str, expected: str) -> bool:
    """걸리는 시간으로 비밀번호를 추측하지 못하게 일정 시간 비교를 쓴다."""
    return bool(expected) and hmac.compare_digest(given.encode("utf-8"), expected.encode("utf-8"))


def safe_next(target: str | None) -> str:
    """로그인 뒤 돌아갈 주소. 이 사이트 안의 경로만 허용한다(다른 사이트로 보내는 주소 차단)."""
    if not target or not target.startswith("/") or target.startswith("//") or "\\" in target:
        return "/"
    return target


class LoginLimiter:
    """같은 주소에서 틀린 비밀번호가 반복되면 잠시 로그인 시도를 막는다 (메모리에만 보관)."""

    def __init__(self, max_failures: int = 5, window_seconds: int = 300, max_clients: int = 2000):
        self.max_failures = max_failures
        self.window = window_seconds
        self.max_clients = max_clients
        self._failures: dict[str, list[float]] = {}

    def _recent(self, client: str, now: float) -> list[float]:
        recent = [t for t in self._failures.get(client, []) if now - t < self.window]
        if recent:
            self._failures[client] = recent
        else:
            self._failures.pop(client, None)
        return recent

    def retry_after(self, client: str, now: float | None = None) -> int:
        """막혀 있으면 다시 시도할 수 있을 때까지 남은 초, 아니면 0."""
        now = time.time() if now is None else now
        recent = self._recent(client, now)
        if len(recent) < self.max_failures:
            return 0
        return max(1, int(self.window - (now - recent[0])))

    def record_failure(self, client: str, now: float | None = None) -> None:
        now = time.time() if now is None else now
        self._failures[client] = self._recent(client, now) + [now]
        # 수많은 주소에서 시도가 들어와도 기록이 끝없이 쌓이지 않게, 지난 기록부터 버린다
        if len(self._failures) > self.max_clients:
            for other in list(self._failures):
                self._recent(other, now)
            while len(self._failures) > self.max_clients:
                oldest = min(self._failures, key=lambda c: self._failures[c][-1])
                del self._failures[oldest]

    def reset(self, client: str) -> None:
        self._failures.pop(client, None)


def same_origin(origin_header: str | None, host_header: str | None, allowed_hosts=()) -> bool:
    """Origin 이 없거나(브라우저가 아님) 이 서버의 주소와 같으면 True."""
    if origin_header is None:
        return True
    origin_host = host_name(urlsplit(origin_header).netloc)
    if not origin_host:
        return False            # 'null' 등: 출처를 알 수 없는 페이지
    return origin_host == host_name(host_header) or origin_host in {h.lower() for h in allowed_hosts}


def decide(*, path: str, client_host: str | None, host_header: str | None,
           password_set: bool, authenticated: bool,
           require_loopback_auth: bool = False, allowed_hosts=(),
           method: str = "GET", origin_header: str | None = None) -> str:
    """요청을 어떻게 처리할지: allow · login(로그인 페이지로) · unauthorized(401) · forbidden · bad_host · bad_origin(403).

    순서가 중요하다. 로그인 없이 통과시키는 경우(루프백 신뢰)에만 Host 를 검사한다.
    """
    if method.upper() in UNSAFE_METHODS and not same_origin(origin_header, host_header, allowed_hosts):
        return "bad_origin"
    local = is_loopback(client_host)
    if not password_set:
        if not local:
            return "forbidden"          # 비밀번호가 없으면 이 PC 밖에서는 쓸 수 없다
        trusted = True
    else:
        if path in OPEN_PATHS or authenticated:
            return "allow"
        trusted = local and not require_loopback_auth
        if not trusted:
            return "unauthorized" if path.startswith("/api/") else "login"
    if trusted and host_name(host_header) not in LOOPBACK_HOSTS | {h.lower() for h in allowed_hosts}:
        return "bad_host"
    return "allow"
