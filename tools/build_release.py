"""Build a source-only release from an allowlist; never include production data."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import zipfile

RELEASE_FILES = ('.env.example', '.gitignore', 'README.md', 'bootstrap.py', 'config.py', 'constants.py', 'main.py', 'maxbot/__init__.py', 'maxbot/callbacks.py', 'maxbot/certs/russian_trusted_root_ca.pem', 'maxbot/client.py', 'maxbot/instance_lock.py', 'maxbot/keyboards.py', 'maxbot/logging_utils.py', 'maxbot/models.py', 'maxbot/normalizer.py', 'maxbot/service.py', 'maxbot/storage.py', 'maxbot/tls.py', 'max-support-bot.spec', 'pyproject.toml', 'requirements-windows-build.txt', 'tests/test_bootstrap.py', 'tests/test_callbacks.py', 'tests/test_client.py', 'tests/test_config.py', 'tests/test_flow.py', 'tests/test_instance_lock.py', 'tests/test_logging_privacy.py', 'tests/test_main.py', 'tests/test_normalizer.py', 'tests/test_release.py', 'tests/test_routing.py', 'tests/test_service.py', 'tests/test_tls.py', 'tools/build_release.py', 'tools/build_windows.py', 'tools/run_tests.py')


def build_release(root: Path, output: Path) -> list[str]:
    root, output = root.resolve(), output.resolve()
    if output.suffix.lower() != ".zip":
        raise ValueError("Release output must have a .zip extension")
    entries = {}
    for name in RELEASE_FILES:
        source = root / name
        if source.is_symlink() or not source.resolve().is_relative_to(root):
            raise ValueError("Release source must not be a symlink or escape the source directory")
        entries[name] = source.read_bytes()
    manifest = {name: hashlib.sha256(content).hexdigest() for name, content in entries.items()}
    entries["release-manifest.json"] = json.dumps(manifest, indent=2).encode("utf-8")
    output.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation protects old releases, including archives holding live data.
    with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return sorted(entries)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        names = build_release(Path(__file__).resolve().parents[1], args.output)
    except (OSError, ValueError, zipfile.BadZipFile):
        parser.exit(1, "Release not created; check source files and choose a new .zip output.\n")
    print(f"Source release created: {len(names)} files; no production configuration or user data included.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
