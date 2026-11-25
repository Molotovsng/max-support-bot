"""Build a clean Windows x64 executable without reading production config/data."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
from importlib import metadata
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import zipfile

RUNTIME_FILES = (
    "bootstrap.py", "main.py", "config.py", "constants.py", "max-support-bot.spec",
    "maxbot/__init__.py", "maxbot/callbacks.py", "maxbot/client.py", "maxbot/models.py",
    "maxbot/normalizer.py", "maxbot/service.py", "maxbot/storage.py",
    "maxbot/instance_lock.py", "maxbot/keyboards.py", "maxbot/logging_utils.py",
    "maxbot/tls.py", "maxbot/certs/russian_trusted_root_ca.pem",
)


def build(output: Path) -> Path:
    if sys.platform != "win32" or struct.calcsize("P") != 8:
        raise RuntimeError("Build requires 64-bit Windows Python")
    root = Path(__file__).resolve().parents[1]
    output = output.resolve()
    if not output.is_relative_to(root / "releases") or output == root / "releases":
        raise ValueError("Choose a new directory inside releases")
    zipped = output.with_suffix(".zip")
    if output.exists() or zipped.exists():
        raise FileExistsError("Output already exists; choose a new release name")
    workspace = root / ".audit" / "exe-builds"
    workspace.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix="windows-x64-", dir=workspace))
    source = stage / "source"
    source.mkdir()
    source_hashes = {}
    for name in RUNTIME_FILES:
        path = root / name
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            raise ValueError("Unsafe build source")
        target = source / name
        target.parent.mkdir(parents=True, exist_ok=True)
        content = path.read_bytes()
        target.write_bytes(content)
        source_hashes[name] = hashlib.sha256(content).hexdigest()
    env = os.environ.copy()
    for name in list(env):
        if name.startswith(("MAX_", "APP_", "DEPARTMENT_")) or name in {"USERS_FILE", "BOT_PLATFORM", "SPECIALIST_IDS", "PYTHONPATH", "PYTHONHOME"}:
            del env[name]
    temporary = stage / "tmp"
    temporary.mkdir()
    env.update({"TEMP": str(temporary), "TMP": str(temporary), "PYINSTALLER_CONFIG_DIR": str(stage / "cache"), "PYTHONDONTWRITEBYTECODE": "1", "PYTHON_DOTENV_DISABLED": "1"})
    log = stage / "pyinstaller.log"
    with log.open("w", encoding="utf-8") as stream:
        subprocess.run([
            sys.executable, "-B", "-m", "PyInstaller", "--noconfirm", "--clean",
            "--distpath", str(stage / "dist"), "--workpath", str(stage / "work"),
            str(source / "max-support-bot.spec"),
        ], cwd=source, env=env, stdout=stream, stderr=subprocess.STDOUT, check=True)
    executable = stage / "dist" / "max-support-bot.exe"
    check = subprocess.run([str(executable), "--check"], cwd=source, env=env, capture_output=True, text=True, timeout=120)
    (stage / "offline-check.txt").write_text(check.stdout + check.stderr, encoding="utf-8")
    if check.returncode != 0 or json.loads(check.stdout).get("ok") is not True:
        raise RuntimeError("Executable offline check failed; inspect .audit/exe-builds")
    output.mkdir(parents=True)
    shutil.copyfile(executable, output / "max-support-bot.exe")
    for name in (".env.example", "README.md", "requirements-windows-build.txt"):
        shutil.copyfile(root / name, output / name)
    start = '@echo off\r\nsetlocal\r\ncd /d "%~dp0"\r\nif not exist ".env" (\r\n  echo Create .env using .env.example. Read README.md.\r\n  pause\r\n  exit /b 1\r\n)\r\nmax-support-bot.exe\r\nset "bot_exit=%errorlevel%"\r\necho Bot stopped. Read bot.log if an error occurred.\r\npause\r\nexit /b %bot_exit%\r\n'
    (output / "start_bot.bat").write_bytes(start.encode("ascii"))
    (output / "check_bot.bat").write_bytes(b'@echo off\r\ncd /d "%~dp0"\r\nmax-support-bot.exe --check\r\nset "check_exit=%errorlevel%"\r\npause\r\nexit /b %check_exit%\r\n')
    distributions = {dist.metadata["Name"]: dist.version for dist in metadata.distributions()}
    manifest = {
        "built_at_utc": datetime.now(timezone.utc).isoformat(),
        "platform": "Windows x64", "python": sys.version.split()[0],
        "pyinstaller": metadata.version("pyinstaller"),
        "exe_sha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
        "source_sha256": source_hashes, "dependencies": dict(sorted(distributions.items())),
        "offline_check": json.loads(check.stdout), "bot_started": False,
        "production_config_included": False,
    }
    policy = Path(sys.base_prefix) / "Lib" / "codex-rejected-cas.pem"
    if policy.is_file():
        manifest["interpreter_tls_policy_sha256"] = hashlib.sha256(policy.read_bytes()).hexdigest()
    (output / "build-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    with zipfile.ZipFile(zipped, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(output.iterdir()):
            archive.write(path, output.name + "/" + path.name)
    return zipped


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    path = build(args.output_dir)
    print("Windows x64 executable built; offline check passed; bot not started.")
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
