from __future__ import annotations

import atexit
import os
from pathlib import Path
from subprocess import CalledProcessError, check_output


class InstanceLock:
    def __init__(self, path: str = ".bot.lock") -> None:
        self.path = Path(path)
        self.acquired = False

    def acquire(self) -> None:
        current_pid = os.getpid()

        if self.path.exists():
            try:
                existing_pid = int(self.path.read_text(encoding="utf-8").strip())
            except (OSError, ValueError):
                existing_pid = None

            if existing_pid and self._is_process_running(existing_pid):
                raise RuntimeError(
                    f"Another bot instance is already running with PID {existing_pid}. "
                    "Stop it before starting a new one."
                )
            self.path.unlink(missing_ok=True)

        self.path.write_text(str(current_pid), encoding="utf-8")
        self.acquired = True
        atexit.register(self.release)

    def release(self) -> None:
        if not self.acquired:
            return
        try:
            if self.path.exists():
                lock_pid = self.path.read_text(encoding="utf-8").strip()
                if lock_pid == str(os.getpid()):
                    self.path.unlink()
        except OSError:
            pass
        finally:
            self.acquired = False

    def _is_process_running(self, pid: int) -> bool:
        if pid <= 0:
            return False
        try:
            if os.name == "nt":
                output = check_output(
                    ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                    text=True,
                )
                return str(pid) in output and "INFO:" not in output
            os.kill(pid, 0)
        except (OSError, CalledProcessError):
            return False
        return True
