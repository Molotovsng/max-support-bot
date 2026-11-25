"""Run tests without production .env, logs, data files or external HTTP access."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dependency-dir", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    sys.dont_write_bytecode = True
    if args.dependency_dir:
        sys.path.insert(0, str(args.dependency_dir.resolve()))
    sys.path.insert(0, str(root))
    import dotenv
    import httpx

    temp_root = root / ".audit" / "tmp"
    temp_root.mkdir(parents=True, exist_ok=True)
    tempfile.tempdir = str(temp_root)
    with tempfile.TemporaryDirectory(dir=temp_root) as directory:
        previous = Path.cwd()
        try:
            os.chdir(directory)
            with (
                patch.object(dotenv, "load_dotenv"),
                patch.object(httpx.HTTPTransport, "handle_request", side_effect=AssertionError("External HTTP disabled in tests")),
                patch.object(httpx.AsyncHTTPTransport, "handle_async_request", side_effect=AssertionError("External HTTP disabled in tests")),
            ):
                suite = unittest.defaultTestLoader.discover(str(root / "tests"))
                result = unittest.TextTestRunner(verbosity=2).run(suite)
        finally:
            os.chdir(previous)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
