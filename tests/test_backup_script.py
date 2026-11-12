"""로컬 자료 묶음 스크립트: 가짜 프로젝트 폴더로만 시험한다 (실제 자료를 묶지 않음)."""
import os
import shutil
import stat
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "backup-local-data.sh"


@unittest.skipUnless(shutil.which("bash") and shutil.which("tar"), "bash/tar 없음")
class BackupScriptTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name)
        self.project = base / "project"
        self.outside = base / "outside"
        (self.project / "data" / "eval").mkdir(parents=True)
        (self.project / "uploads" / "documents").mkdir(parents=True)
        self.outside.mkdir()
        (self.project / "data" / "eval" / "questions.jsonl").write_text("{}\n", encoding="utf-8")
        (self.project / "uploads" / "documents" / "a.pdf").write_bytes(b"%PDF-1.4 fake")
        (self.project / ".env").write_text("ES_PASSWORD=not-a-real-password\n", encoding="utf-8")
        (self.project / "app.py").write_text("# source code is not backed up\n", encoding="utf-8")

    def run_script(self, *args):
        env = dict(os.environ, LANGCHAIN_LAB_DIR=str(self.project), HOME=str(self.outside))
        return subprocess.run(["bash", str(SCRIPT), *args], capture_output=True, text=True, env=env)

    def snapshot(self):
        return {str(p.relative_to(self.project)): p.read_bytes() for p in self.project.rglob("*") if p.is_file()}

    def test_list_creates_nothing(self):
        before = self.snapshot()
        result = self.run_script("--list")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("파일은 만들지 않았습니다", result.stdout)
        self.assertEqual(list(self.outside.iterdir()), [])
        self.assertEqual(self.snapshot(), before)

    def test_archive_contains_local_data_only_and_is_private(self):
        before = self.snapshot()
        target = self.outside / "backup.tar.gz"
        result = self.run_script(str(target))
        self.assertEqual(result.returncode, 0, result.stderr)
        with tarfile.open(target) as archive:
            names = set(archive.getnames())
        self.assertIn(".env", names)
        self.assertIn("data/eval/questions.jsonl", names)
        self.assertIn("uploads/documents/a.pdf", names)
        self.assertNotIn("app.py", names)
        self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)
        self.assertEqual(self.snapshot(), before)          # 원본은 그대로
        self.assertNotIn("not-a-real-password", result.stdout)

    def test_default_name_goes_to_home_not_into_the_project(self):
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stderr)
        created = list(self.outside.glob("langchain-lab-backup-*.tar.gz"))
        self.assertEqual(len(created), 1)

    def test_refuses_to_write_inside_the_project(self):
        result = self.run_script(str(self.project / "data" / "backup.tar.gz"))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("프로젝트 폴더 안에는 만들지 않습니다", result.stdout)
        self.assertFalse((self.project / "data" / "backup.tar.gz").exists())

    def test_never_overwrites_an_existing_file(self):
        target = self.outside / "backup.tar.gz"
        target.write_text("keep me", encoding="utf-8")
        result = self.run_script(str(target))
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(target.read_text(encoding="utf-8"), "keep me")

    def test_missing_parts_are_skipped_and_empty_project_is_reported(self):
        shutil.rmtree(self.project / "uploads")
        result = self.run_script("--list")
        self.assertIn("uploads 없음", result.stdout)
        shutil.rmtree(self.project / "data")
        (self.project / ".env").unlink()
        self.assertNotEqual(self.run_script("--list").returncode, 0)


if __name__ == "__main__":
    unittest.main()
