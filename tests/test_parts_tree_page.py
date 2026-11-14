import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

import app


class PartsTreePageTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app.app, base_url="http://127.0.0.1:8000", client=("127.0.0.1", 50000))

    def test_page_and_api(self):
        self.assertEqual(self.client.get("/parts-tree").status_code, 200)
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "data" / "parts_tree").mkdir(parents=True)
            (root / "data" / "parts_tree" / "tree.json").write_text(json.dumps({"domains": [{"id": "power"}], "unmapped": []}))
            with mock.patch.object(app, "ROOT", root):
                self.assertEqual(self.client.get("/api/parts-tree").json()["domains"], [{"id": "power"}])
        with tempfile.TemporaryDirectory() as d, mock.patch.object(app, "ROOT", Path(d)):
            self.assertEqual(self.client.get("/api/parts-tree").json()["domains"], [])


if __name__ == "__main__":
    unittest.main()
