import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scholarly_translation import web_ui

ROOT = Path(__file__).resolve().parent.parent
CLAIM = "import sys; from pathlib import Path; from scholarly_translation import web_ui; " \
        "print(web_ui.claim_single_instance(Path(sys.argv[1])) is not None)"


class SingleInstanceTests(unittest.TestCase):
    def claim_elsewhere(self, folder):
        result = subprocess.run([sys.executable, "-B", "-c", CLAIM, str(folder)], cwd=ROOT,
                                capture_output=True, text=True, timeout=60, check=True)
        return result.stdout.strip() == "True"

    def test_second_server_on_the_same_folder_is_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            held = web_ui.claim_single_instance(Path(folder))
            self.assertIsNotNone(held)
            try:
                self.assertFalse(self.claim_elsewhere(folder))
            finally:
                held.close()
            # Released on close (and by the OS when a server dies).
            self.assertTrue(self.claim_elsewhere(folder))

    def test_running_url_accepts_only_a_local_ui_address(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            self.assertIsNone(web_ui.running_instance_url(folder))
            (folder / "web_ui.url").write_text("http://127.0.0.1:50756/\n", encoding="utf-8")
            self.assertEqual(web_ui.running_instance_url(folder), "http://127.0.0.1:50756/")
            (folder / "web_ui.url").write_text("https://example.com/", encoding="utf-8")
            self.assertIsNone(web_ui.running_instance_url(folder))


if __name__ == "__main__":
    unittest.main()
