import hashlib
import os
import ssl
import tempfile
import unittest
import certifi
from pathlib import Path
from unittest.mock import patch

from maxbot.tls import DEFAULT_API_BASE, DEFAULT_ROOT_CA, ROOT_CA_SHA256, build_ssl_context, validate_api_base


class TLSTests(unittest.TestCase):
    def test_bundled_root_has_verified_fingerprint(self):
        der = ssl.PEM_cert_to_DER_cert(DEFAULT_ROOT_CA.read_text(encoding="ascii"))
        self.assertEqual(hashlib.sha256(der).hexdigest(), ROOT_CA_SHA256)

    def test_context_verifies_hosts_and_retains_normal_roots(self):
        baseline = ssl.create_default_context(cafile=certifi.where())
        context = build_ssl_context()
        self.assertTrue(context.check_hostname)
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        roots = {hashlib.sha256(c).hexdigest() for c in context.get_ca_certs(binary_form=True)}
        self.assertIn(ROOT_CA_SHA256, roots)
        self.assertTrue(set(baseline.get_ca_certs(binary_form=True)) <= set(context.get_ca_certs(binary_form=True)))

    def test_context_does_not_depend_on_proxy_or_ca_environment(self):
        with patch.dict(os.environ, {"SSL_CERT_FILE": "missing-private-path", "SSL_CERT_DIR": "missing-private-path"}):
            # Explicit default CA selection must not be replaced by env variables.
            with patch("maxbot.tls.ssl.create_default_context", wraps=ssl.create_default_context) as factory:
                context = build_ssl_context()
        self.assertTrue(context.check_hostname)
        factory.assert_called_once()

    def test_invalid_or_missing_root_is_rejected_without_leaking_path(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "private-name.pem"
            for contents in (None, "not a certificate", DEFAULT_ROOT_CA.read_text() * 2):
                if contents is not None:
                    path.write_text(contents)
                with self.assertRaises(RuntimeError) as caught:
                    build_ssl_context(path)
                self.assertNotIn("private-name", str(caught.exception))

    def test_unsafe_or_retired_api_origins_are_rejected(self):
        for origin in ("http://platform-api2.max.ru", "https://platform-api.max.ru", "https://token:secret@example.com", "https://example.com?token=secret", "https://example.com:8000", "https://example.com/api"):
            with self.subTest(origin=origin), self.assertRaises(ValueError):
                validate_api_base(origin)
        self.assertEqual(validate_api_base(DEFAULT_API_BASE + "/"), DEFAULT_API_BASE)
