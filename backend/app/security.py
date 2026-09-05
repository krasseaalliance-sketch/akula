import base64
import binascii
import hashlib
import hmac
import json
import os
import secrets
from datetime import datetime, timedelta


def _secret() -> str:
    return os.getenv("JWT_SECRET", "change-me-in-a-secret-store")


def _expire_minutes() -> int:
    return int(os.getenv("JWT_EXPIRE_MINUTES", "30"))


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 310_000)
    return f"pbkdf2_sha256$310000${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, rounds, salt_hex, digest_hex = encoded.split("$")
        if algorithm != "pbkdf2_sha256":
            return False
        candidate = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), bytes.fromhex(salt_hex), int(rounds)
        )
        return hmac.compare_digest(candidate.hex(), digest_hex)
    except (ValueError, TypeError):
        return False


def create_access_token(user_id: str) -> str:
    now = datetime.utcnow()
    exp = now + timedelta(minutes=_expire_minutes())
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {"sub": user_id, "iat": int(now.timestamp()), "exp": int(exp.timestamp())}

    def encode(value: dict) -> str:
        return (
            base64.urlsafe_b64encode(json.dumps(value, separators=(",", ":")).encode())
            .rstrip(b"=")
            .decode()
        )

    unsigned = f"{encode(header)}.{encode(payload)}"
    signature = hmac.new(_secret().encode(), unsigned.encode(), hashlib.sha256).digest()
    return f"{unsigned}.{base64.urlsafe_b64encode(signature).rstrip(b'=').decode()}"


def decode_access_token(token: str) -> str | None:
    try:
        encoded_header, encoded_payload, encoded_signature = token.split(".")
        unsigned = f"{encoded_header}.{encoded_payload}"
        expected = hmac.new(_secret().encode(), unsigned.encode(), hashlib.sha256).digest()
        provided = base64.urlsafe_b64decode(encoded_signature + "=" * (-len(encoded_signature) % 4))
        if not hmac.compare_digest(expected, provided):
            return None
        payload = json.loads(
            base64.urlsafe_b64decode(encoded_payload + "=" * (-len(encoded_payload) % 4))
        )
        if int(payload["exp"]) < int(datetime.utcnow().timestamp()):
            return None
        return str(payload["sub"])
    except (
        ValueError,
        KeyError,
        TypeError,
        UnicodeDecodeError,
        binascii.Error,
        json.JSONDecodeError,
    ):
        return None
