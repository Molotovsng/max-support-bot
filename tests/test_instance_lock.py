import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from maxbot.instance_lock import InstanceLock


class InstanceLockTests(unittest.TestCase):
    def test_rejects_second_running_instance(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            lock_path = Path(tmpdir) / ".bot.lock"
            lock_path.write_text("99999", encoding="utf-8")

            lock = InstanceLock(str(lock_path))

            with patch.object(lock, "_is_process_running", return_value=True):
                with self.assertRaises(RuntimeError):
                    lock.acquire()


if __name__ == "__main__":
    unittest.main()
