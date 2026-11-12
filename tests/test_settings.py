"""settings.py: .env → 환경변수 → 기본값 순서와 기본값 보존 테스트."""
import os
import unittest
from unittest import mock

import settings


class SettingsTests(unittest.TestCase):
    def test_env_file_wins_over_environment(self):
        with mock.patch.dict(settings._VALUES, {"CHAT_MODEL": "from-env-file"}, clear=True), \
             mock.patch.dict(os.environ, {"CHAT_MODEL": "from-process-env"}):
            self.assertEqual(settings.get("CHAT_MODEL", "default"), "from-env-file")

    def test_environment_then_default(self):
        with mock.patch.dict(settings._VALUES, {}, clear=True), \
             mock.patch.dict(os.environ, {"CHAT_MODEL": "from-process-env"}):
            self.assertEqual(settings.get("CHAT_MODEL", "default"), "from-process-env")
        with mock.patch.dict(settings._VALUES, {}, clear=True), \
             mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(settings.get("CHAT_MODEL", "default"), "default")

    def test_int_and_list_parsing(self):
        with mock.patch.dict(settings._VALUES, {"N": "abc", "L": " a, b ,,c "}, clear=True):
            self.assertEqual(settings.get_int("N", 7), 7)
            self.assertEqual(settings.get_list("L"), ["a", "b", "c"])

    def test_describe_hides_secrets(self):
        text = repr(settings.describe())
        self.assertNotIn("API_KEY", text.upper().replace("CONFIGURED", ""))
        for secret in (settings.OPENAI_API_KEY, settings.ANTHROPIC_API_KEY):
            if secret:
                self.assertNotIn(secret, text)


if __name__ == "__main__":
    unittest.main()
