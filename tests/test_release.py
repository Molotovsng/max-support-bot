import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from tools.build_release import RELEASE_FILES, build_release


class ReleaseTests(unittest.TestCase):
    def test_release_excludes_live_data_and_contains_verified_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in RELEASE_FILES:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("source fixture", encoding="utf-8")
            for name in (".env", "bot_users.json", "appeal_links.json", "bot.log", "old.zip"):
                (root / name).write_text("PRIVATE_CANARY", encoding="utf-8")
            output = root / "releases" / "clean.zip"
            build_release(root, output)
            with zipfile.ZipFile(output) as archive:
                manifest = json.loads(archive.read("release-manifest.json"))
                for name in archive.namelist():
                    self.assertNotIn(b"PRIVATE_CANARY", archive.read(name))
                    if name != "release-manifest.json":
                        self.assertEqual(hashlib.sha256(archive.read(name)).hexdigest(), manifest[name])
            original = output.read_bytes()
            with self.assertRaises(FileExistsError):
                build_release(root, output)
            self.assertEqual(output.read_bytes(), original)

    def test_non_zip_output_cannot_replace_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / ".env"
            target.write_text("PRIVATE_CANARY")
            with self.assertRaises(ValueError):
                build_release(root, target)
            self.assertEqual(target.read_text(), "PRIVATE_CANARY")
