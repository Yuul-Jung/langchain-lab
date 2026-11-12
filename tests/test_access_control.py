"""접근 제어: 이 PC 전용(기본) · 비밀번호 로그인 · Host/Origin 검사 (서버·모델 없이 실행)."""
import importlib.util
import unittest
from unittest import mock

import access_control as ac

SECRET = b"test-secret"


def decide(**kw):
    base = dict(path="/documents", client_host="127.0.0.1", host_header="127.0.0.1:8000",
                password_set=False, authenticated=False)
    base.update(kw)
    return ac.decide(**base)


class DecideLocalOnlyTest(unittest.TestCase):
    """비밀번호를 설정하지 않은 기본 상태."""

    def test_this_pc_is_allowed(self):
        self.assertEqual(decide(), "allow")
        self.assertEqual(decide(host_header="localhost:8000"), "allow")
        self.assertEqual(decide(client_host="::1", host_header="[::1]:8000"), "allow")

    def test_other_devices_are_refused_even_if_the_server_is_exposed(self):
        self.assertEqual(decide(client_host="192.168.0.9", host_header="192.168.0.5:8000"), "forbidden")
        self.assertEqual(decide(client_host=None), "forbidden")
        self.assertEqual(decide(client_host="192.168.0.9", path="/login"), "forbidden")

    def test_foreign_host_name_from_this_pc_is_refused(self):
        # DNS 리바인딩: 요청은 이 PC 의 브라우저에서 오지만 주소 이름이 공격자의 도메인이다
        self.assertEqual(decide(host_header="evil.example:8000"), "bad_host")
        self.assertEqual(decide(host_header=None), "bad_host")
        self.assertEqual(decide(host_header="127.0.0.1.evil.example"), "bad_host")

    def test_extra_host_names_can_be_allowed(self):
        self.assertEqual(decide(host_header="lab.local:8000", allowed_hosts=["LAB.local"]), "allow")


class DecidePasswordTest(unittest.TestCase):
    """ACCESS_PASSWORD 를 설정한 상태."""

    def remote(self, **kw):
        return decide(password_set=True, client_host="192.168.0.9", host_header="192.168.0.5:8000", **kw)

    def test_other_devices_must_log_in(self):
        self.assertEqual(self.remote(), "login")
        self.assertEqual(self.remote(path="/"), "login")
        self.assertEqual(self.remote(path="/api/documents"), "unauthorized")
        self.assertEqual(self.remote(path="/api/status"), "unauthorized")

    def test_login_paths_stay_open(self):
        for path in ("/login", "/api/login", "/api/logout"):
            self.assertEqual(self.remote(path=path), "allow")

    def test_logged_in_device_is_allowed(self):
        self.assertEqual(self.remote(path="/api/documents", authenticated=True), "allow")

    def test_this_pc_still_works_without_login(self):
        self.assertEqual(decide(password_set=True, path="/api/documents"), "allow")

    def test_this_pc_must_log_in_behind_a_local_reverse_proxy(self):
        self.assertEqual(decide(password_set=True, require_loopback_auth=True), "login")
        self.assertEqual(decide(password_set=True, require_loopback_auth=True, authenticated=True), "allow")

    def test_trusted_loopback_still_needs_a_known_host_name(self):
        self.assertEqual(decide(password_set=True, host_header="evil.example"), "bad_host")


class OriginTest(unittest.TestCase):
    def test_same_site_and_non_browser_writes_are_allowed(self):
        self.assertEqual(decide(method="POST", origin_header="http://127.0.0.1:8000"), "allow")
        self.assertEqual(decide(method="POST", origin_header=None), "allow")

    def test_writes_from_another_website_are_refused(self):
        for origin in ("https://evil.example", "http://localhost:8000", "null", "http://127.0.0.1.evil.example:8000"):
            self.assertEqual(decide(method="POST", origin_header=origin), "bad_origin", origin)
        self.assertEqual(decide(method="delete", origin_header="https://evil.example"), "bad_origin")

    def test_reads_from_the_public_start_page_are_not_blocked_here(self):
        # 공개 시작 페이지의 상태 확인(GET /api/status)은 CORS 규칙이 따로 제한한다
        self.assertEqual(decide(method="GET", path="/api/status", origin_header="https://yuul-jung.github.io"), "allow")

    def test_origin_check_also_applies_to_logged_in_sessions(self):
        self.assertEqual(decide(password_set=True, authenticated=True, client_host="192.168.0.9",
                                host_header="192.168.0.5:8000", method="POST",
                                origin_header="https://evil.example"), "bad_origin")

    def test_proxy_domain_can_be_allowed(self):
        self.assertEqual(decide(method="POST", origin_header="https://lab.example.com",
                                allowed_hosts=["lab.example.com"]), "allow")


class CrossSiteBackgroundTest(unittest.TestCase):
    """다른 사이트의 페이지가 뒤에서 보내는 요청 (Sec-Fetch-* 표시)."""

    def test_background_requests_from_other_sites_are_refused(self):
        heavy = "/api/documents/maintenance/reextract-preview"
        self.assertEqual(decide(path=heavy, fetch_site="cross-site", fetch_mode="no-cors", fetch_dest="image"), "bad_origin")
        self.assertEqual(decide(path=heavy, fetch_site="cross-site", fetch_mode="cors", fetch_dest="empty"), "bad_origin")
        self.assertEqual(decide(path="/documents", fetch_site="cross-site", fetch_mode="navigate", fetch_dest="iframe"), "bad_origin")

    def test_links_opened_from_the_public_start_page_still_work(self):
        for path in ("/", "/documents", "/api/documents/health/status"):
            self.assertEqual(decide(path=path, fetch_site="cross-site", fetch_mode="navigate", fetch_dest="document"), "allow")

    def test_public_status_check_is_the_one_exception(self):
        self.assertEqual(decide(path="/api/status", fetch_site="cross-site", fetch_mode="cors", fetch_dest="empty",
                                origin_header="https://yuul-jung.github.io"), "allow")

    def test_same_site_and_headerless_requests_are_unaffected(self):
        self.assertEqual(decide(path="/api/documents", fetch_site="same-origin", fetch_mode="cors", fetch_dest="empty"), "allow")
        self.assertEqual(decide(path="/api/documents", fetch_site="none", fetch_mode="navigate", fetch_dest="document"), "allow")
        self.assertEqual(decide(path="/api/documents"), "allow")           # curl, 오래된 브라우저


class TokenAndHelpersTest(unittest.TestCase):
    def test_token_round_trip_and_expiry(self):
        token = ac.make_token(SECRET, hours=1, now=1000)
        self.assertTrue(ac.token_valid(token, SECRET, now=1000 + 3599))
        self.assertFalse(ac.token_valid(token, SECRET, now=1000 + 3600))

    def test_tampered_or_malformed_tokens_are_rejected(self):
        token = ac.make_token(SECRET, hours=1, now=1000)
        expires, signature = token.split(".")
        forged = f"{int(expires) + 99999}.{signature}"
        for bad in (forged, token + "x", "abc", "", None, "1.2.3", f"{expires}.", f".{signature}", "-5.abc"):
            self.assertFalse(ac.token_valid(bad, SECRET, now=1000), bad)
        self.assertFalse(ac.token_valid(token, b"other-secret", now=1000))

    def test_password_comparison(self):
        self.assertTrue(ac.password_matches("길고 어려운 비밀번호", "길고 어려운 비밀번호"))
        self.assertFalse(ac.password_matches("틀림", "길고 어려운 비밀번호"))
        self.assertFalse(ac.password_matches("", ""))

    def test_host_name_parsing(self):
        self.assertEqual(ac.host_name("127.0.0.1:8000"), "127.0.0.1")
        self.assertEqual(ac.host_name("LocalHost"), "localhost")
        self.assertEqual(ac.host_name("[::1]:8000"), "::1")
        self.assertEqual(ac.host_name(None), "")

    def test_next_address_stays_inside_this_site(self):
        self.assertEqual(ac.safe_next("/documents"), "/documents")
        for bad in (None, "", "https://evil.example", "//evil.example", "/\\evil.example", "documents"):
            self.assertEqual(ac.safe_next(bad), "/", bad)

    def test_loopback_detection(self):
        self.assertTrue(ac.is_loopback("127.0.0.1") and ac.is_loopback("127.5.5.5") and ac.is_loopback("::1"))
        self.assertFalse(ac.is_loopback("192.168.0.9") or ac.is_loopback("testclient") or ac.is_loopback(""))

    def test_ipv4_mapped_loopback_is_this_pc(self):
        self.assertTrue(ac.is_loopback("::ffff:127.0.0.1"))
        self.assertFalse(ac.is_loopback("::ffff:192.168.0.9"))
        self.assertFalse(ac.is_loopback("127.0.0.1.evil.example"))

    def test_login_limiter_memory_is_bounded(self):
        limiter = ac.LoginLimiter(max_failures=5, window_seconds=300, max_clients=50)
        for n in range(500):
            limiter.record_failure(f"10.0.{n // 250}.{n % 250}", now=1000 + n * 0.01)
        self.assertLessEqual(len(limiter._failures), 50)
        # 방금 실패한 주소의 기록은 남아 있어야 한다
        limiter.record_failure("10.9.9.9", now=2000)
        self.assertIn("10.9.9.9", limiter._failures)
        # 오래된 기록은 창이 지나면 차단에 쓰이지 않고, 그 주소를 다시 볼 때 지워진다
        self.assertEqual(limiter.retry_after("10.9.9.9", now=5000), 0)
        self.assertNotIn("10.9.9.9", limiter._failures)
        self.assertLessEqual(len(limiter._failures), 50)

    def test_login_limiter_blocks_then_recovers(self):
        limiter = ac.LoginLimiter(max_failures=3, window_seconds=60)
        for second in range(3):
            self.assertEqual(limiter.retry_after("a", now=second), 0)
            limiter.record_failure("a", now=second)
        self.assertEqual(limiter.retry_after("a", now=10), 50)
        self.assertEqual(limiter.retry_after("b", now=10), 0)      # 다른 주소는 영향 없음
        self.assertEqual(limiter.retry_after("a", now=61), 0)      # 시간이 지나면 풀림
        limiter.record_failure("a", now=100)
        limiter.reset("a")
        self.assertEqual(limiter.retry_after("a", now=100), 0)


@unittest.skipUnless(importlib.util.find_spec("fastapi") and importlib.util.find_spec("httpx"),
                     "fastapi/httpx 미설치")
class AppAccessTest(unittest.TestCase):
    def setUp(self):
        from fastapi.testclient import TestClient
        import app
        self.app, self.TestClient = app, TestClient
        app._LOGIN_LIMITER = ac.LoginLimiter()

    def local(self):
        return self.TestClient(self.app.app, base_url="http://127.0.0.1:8000", client=("127.0.0.1", 50000))

    def remote(self):
        return self.TestClient(self.app.app, base_url="http://192.168.0.5:8000", client=("192.168.0.9", 50000),
                               follow_redirects=False)

    def password(self, value="correct horse battery"):
        return mock.patch.object(self.app.settings, "ACCESS_PASSWORD", value)

    def test_default_is_this_pc_only(self):
        self.assertEqual(self.local().get("/documents").status_code, 200)
        r = self.remote().get("/documents")
        self.assertEqual(r.status_code, 403)
        self.assertIn("ACCESS_PASSWORD", r.json()["detail"])

    def test_foreign_host_and_origin_are_refused_locally(self):
        client = self.local()
        self.assertEqual(client.get("/documents", headers={"Host": "evil.example"}).status_code, 403)
        r = client.post("/api/documents/search", json={"query": "x"}, headers={"Origin": "https://evil.example"})
        self.assertEqual(r.status_code, 403)
        self.assertIn("다른 웹사이트", r.json()["detail"])
        background = client.get("/api/documents/maintenance/reextract-preview",
                                headers={"Sec-Fetch-Site": "cross-site", "Sec-Fetch-Mode": "no-cors", "Sec-Fetch-Dest": "image"})
        self.assertEqual(background.status_code, 403)
        opened = client.get("/documents", headers={"Sec-Fetch-Site": "cross-site", "Sec-Fetch-Mode": "navigate",
                                                   "Sec-Fetch-Dest": "document"})
        self.assertEqual(opened.status_code, 200)

    def test_login_is_refused_when_no_password_is_configured(self):
        self.assertEqual(self.local().post("/api/login", json={"password": "x"}).status_code, 400)

    def test_remote_device_logs_in_and_gets_a_session(self):
        with self.password():
            client = self.remote()
            self.assertEqual(client.get("/api/documents").status_code, 401)
            page = client.get("/documents")
            self.assertEqual((page.status_code, page.headers["location"]), (303, "/login?next=/documents"))
            self.assertEqual(client.get("/login").status_code, 200)
            self.assertEqual(client.post("/api/login", json={"password": "wrong"}).status_code, 401)
            r = client.post("/api/login", json={"password": "correct horse battery"})
            self.assertEqual(r.status_code, 200)
            cookie = r.headers["set-cookie"].lower()
            self.assertIn("httponly", cookie)
            self.assertIn("samesite=strict", cookie)
            self.assertEqual(client.get("/documents").status_code, 200)
            self.assertEqual(client.post("/api/logout").status_code, 200)
            self.assertEqual(client.get("/api/documents").status_code, 401)

    def test_bearer_token_from_login_works_for_scripts(self):
        with self.password():
            token = self.remote().post("/api/login", json={"password": "correct horse battery"}).json()["token"]
            fresh = self.remote()
            self.assertEqual(fresh.get("/documents", headers={"Authorization": "Bearer " + token}).status_code, 200)
            self.assertEqual(fresh.get("/documents", headers={"Authorization": "Bearer " + token + "x"}).status_code, 303)

    def test_repeated_wrong_passwords_are_slowed_down(self):
        with self.password():
            client = self.remote()
            for _ in range(5):
                self.assertEqual(client.post("/api/login", json={"password": "wrong"}).status_code, 401)
            blocked = client.post("/api/login", json={"password": "correct horse battery"})
            self.assertEqual(blocked.status_code, 429)
            self.assertIn("retry-after", blocked.headers)

    def test_this_pc_needs_no_login_unless_configured(self):
        with self.password():
            self.assertEqual(self.local().get("/documents").status_code, 200)
            with mock.patch.object(self.app.settings, "AUTH_REQUIRE_LOOPBACK", True):
                r = self.TestClient(self.app.app, base_url="http://127.0.0.1:8000", client=("127.0.0.1", 50000),
                                    follow_redirects=False).get("/documents")
                self.assertEqual(r.status_code, 303)

    def test_status_reports_access_mode_without_secrets(self):
        es = mock.Mock()
        es.info.return_value = {"version": {"number": "9.5.6"}}
        with mock.patch.object(self.app, "fetch_model_states", return_value=[]), \
             mock.patch.object(self.app, "es_client", return_value=es):
            self.assertEqual(self.local().get("/api/status").json()["access_mode"], "local-only")
            with self.password("s3cret-value"):
                body = self.local().get("/api/status")
                self.assertEqual(body.json()["access_mode"], "password")
                self.assertNotIn("s3cret-value", body.text)


if __name__ == "__main__":
    unittest.main()
