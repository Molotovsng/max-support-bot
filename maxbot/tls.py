from __future__ import annotations

import hashlib
import ssl
from pathlib import Path
from urllib.parse import urlsplit

import certifi

DEFAULT_API_BASE = "https://platform-api2.max.ru"
ROOT_CA_SHA256 = "d26d2d0231b7c39f92cc738512ba54103519e4405d68b5bd703e9788ca8ecf31"
DEFAULT_ROOT_CA = Path(__file__).with_name("certs") / "russian_trusted_root_ca.pem"


def validate_api_base(value: str) -> str:
    """Reject unsafe origins without including their potentially secret contents."""
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        raise ValueError("MAX_API_BASE must be a valid HTTPS origin") from None
    if parsed.hostname and parsed.hostname.rstrip(".") == "platform-api.max.ru":
        raise ValueError("MAX_API_BASE uses the retired host; configure https://platform-api2.max.ru")
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
        or port not in {None, 443}
        or any(character.isspace() for character in value)
    ):
        raise ValueError("MAX_API_BASE must be an HTTPS origin on port 443 without credentials or parameters")
    return value.rstrip("/")


def build_ssl_context(root_ca_path: str | Path | None = None) -> ssl.SSLContext:
    """Add the verified MAX root to normal system CAs, independently of proxies."""
    path = Path(root_ca_path) if root_ca_path else DEFAULT_ROOT_CA
    try:
        pem = path.read_text(encoding="ascii")
        if pem.count("-----BEGIN CERTIFICATE-----") != 1:
            raise ValueError("Expected one root certificate")
        der = ssl.PEM_cert_to_DER_cert(pem)
        if hashlib.sha256(der).hexdigest() != ROOT_CA_SHA256:
            raise ValueError("Unexpected root certificate")
        context = ssl.create_default_context(cafile=certifi.where())
        context.load_verify_locations(cadata=pem)
    except (OSError, ValueError, UnicodeError, ssl.SSLError):
        raise RuntimeError("MAX root CA is missing or invalid; supply the verified Russian Trusted Root CA") from None
    return context
