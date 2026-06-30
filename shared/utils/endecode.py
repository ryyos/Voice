from __future__ import annotations

import base64
import hashlib
import hmac
import json
import struct
import time
from urllib.parse import quote, unquote


class Endecode:
    """
    Encode / decode utility — covers one-way hashing, reversible encoding,
    and simple symmetric encryption (XOR + base64, no extra dependencies).
    """

    @staticmethod
    def md5(text: str, *, encoding: str = "utf-8") -> str:
        """MD5 hex digest — fast, compact, good for dedup IDs / cache keys."""
        return hashlib.md5(text.encode(encoding)).hexdigest()

    @staticmethod
    def sha256(text: str, *, encoding: str = "utf-8") -> str:
        """SHA-256 hex digest — more collision-resistant than MD5."""
        return hashlib.sha256(text.encode(encoding)).hexdigest()

    @staticmethod
    def sha1(text: str, *, encoding: str = "utf-8") -> str:
        """SHA-1 hex digest."""
        return hashlib.sha1(text.encode(encoding)).hexdigest()

    @staticmethod
    def hmac_sha256(text: str, secret: str, *, encoding: str = "utf-8") -> str:
        """HMAC-SHA256 — keyed hash, useful for signing tokens or webhooks."""
        return hmac.new(
            secret.encode(encoding),
            text.encode(encoding),
            hashlib.sha256,
        ).hexdigest()

    @staticmethod
    def b64_encode(text: str, *, encoding: str = "utf-8") -> str:
        """Encode text to Base64 string."""
        return base64.b64encode(text.encode(encoding)).decode("ascii")

    @staticmethod
    def b64_decode(encoded: str, *, encoding: str = "utf-8") -> str:
        """Decode Base64 string back to original text."""
        return base64.b64decode(encoded.encode("ascii")).decode(encoding)

    @staticmethod
    def b64_encode_bytes(data: bytes) -> str:
        """Encode raw bytes to Base64 string."""
        return base64.b64encode(data).decode("ascii")

    @staticmethod
    def b64_decode_bytes(encoded: str) -> bytes:
        """Decode Base64 string back to raw bytes."""
        return base64.b64decode(encoded.encode("ascii"))

    # ── Reversible: URL encoding ──────────────────────────────────────────────

    @staticmethod
    def url_encode(text: str) -> str:
        """Percent-encode a string for safe use in URLs."""
        return quote(text, safe="")

    @staticmethod
    def url_decode(encoded: str) -> str:
        """Decode a percent-encoded URL string."""
        return unquote(encoded)

    # ── Reversible: Hex ───────────────────────────────────────────────────────

    @staticmethod
    def hex_encode(text: str, *, encoding: str = "utf-8") -> str:
        """Encode text to hex string."""
        return text.encode(encoding).hex()

    @staticmethod
    def hex_decode(hex_str: str, *, encoding: str = "utf-8") -> str:
        """Decode hex string back to original text."""
        return bytes.fromhex(hex_str).decode(encoding)

    # ── Reversible: JSON ──────────────────────────────────────────────────────

    @staticmethod
    def json_encode(data: dict | list, *, ensure_ascii: bool = False) -> str:
        """Serialize dict/list to compact JSON string."""
        return json.dumps(data, ensure_ascii=ensure_ascii, separators=(",", ":"))

    @staticmethod
    def json_decode(text: str) -> dict | list:
        """Deserialize JSON string back to dict/list."""
        return json.loads(text)

    # ── Reversible: XOR cipher (simple symmetric, no extra deps) ─────────────

    @staticmethod
    def xor_encode(text: str, key: str, *, encoding: str = "utf-8") -> str:
        """
        XOR cipher — simple symmetric encryption using a repeating key.
        Returns Base64-encoded ciphertext.

        WARNING: XOR is not cryptographically strong. Use for obfuscation only,
        not for protecting sensitive data.

        Example:
            encrypted = Endecode.xor_encode("hello", "mykey")
            original  = Endecode.xor_decode(encrypted, "mykey")
        """
        text_bytes = text.encode(encoding)
        key_bytes  = key.encode(encoding)
        cipher     = bytes(b ^ key_bytes[i % len(key_bytes)] for i, b in enumerate(text_bytes))
        return base64.b64encode(cipher).decode("ascii")

    @staticmethod
    def xor_decode(encoded: str, key: str, *, encoding: str = "utf-8") -> str:
        """Decode a string previously encoded with xor_encode using the same key."""
        key_bytes = key.encode(encoding)
        cipher    = base64.b64decode(encoded.encode("ascii"))
        plain     = bytes(b ^ key_bytes[i % len(key_bytes)] for i, b in enumerate(cipher))
        return plain.decode(encoding)

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def make_id(*parts: str, algo: str = "md5") -> str:
        """
        Build a stable unique ID from one or more strings.
        Joins parts with ':' then hashes.

        Example:
            Endecode.make_id("detik", "https://detik.com/article/123")
            → "a3f2c1..."
        """
        combined = ":".join(parts)
        if algo == "sha256":
            return Endecode.sha256(combined)
        return Endecode.md5(combined)

