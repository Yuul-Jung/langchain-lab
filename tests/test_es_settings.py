"""Offline tests for Elasticsearch credentials loaded in the FastAPI service."""
import base64
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import rag_search


class ElasticsearchSettingsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.env_file = Path(self.temp.name) / ".env"
        self.ca_file = Path(self.temp.name) / "ca.crt"
        self.ca_file.write_text("test-only CA placeholder", encoding="utf-8")

    def test_local_env_overrides_stale_inherited_password(self):
        self.env_file.write_text(
            f'ES_USER="elastic"\nES_PASSWORD="새암호-test"\n'
            f'ES_URL="https://localhost:9200"\nES_CA_CERT="{self.ca_file}"\n',
            encoding="utf-8",
        )
        with patch.object(rag_search, "ENV_FILE", self.env_file), patch.dict(
            "os.environ", {"ES_PASSWORD": "old-password", "ES_USER": "other"}, clear=False
        ):
            settings = rag_search.es_settings()
            self.assertEqual(settings["password"], "새암호-test")
            self.assertEqual(settings["user"], "elastic")
            with patch.object(rag_search, "Elasticsearch") as client:
                rag_search.es_client()
                header = client.call_args.kwargs["headers"]["Authorization"]
                decoded = base64.b64decode(header.removeprefix("Basic ")).decode("utf-8")
                self.assertEqual(decoded, "elastic:새암호-test")
                self.assertNotIn("old-password", header)

    def test_password_reloaded_after_env_change(self):
        with patch.object(rag_search, "ENV_FILE", self.env_file):
            self.env_file.write_text('ES_PASSWORD="first"\n', encoding="utf-8")
            self.assertEqual(rag_search.es_settings()["password"], "first")
            self.env_file.write_text('ES_PASSWORD="second"\n', encoding="utf-8")
            self.assertEqual(rag_search.es_settings()["password"], "second")


if __name__ == "__main__":
    unittest.main()
