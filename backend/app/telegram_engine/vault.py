from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Protocol

from cryptography.fernet import Fernet


class SessionVault(Protocol):
    def store_session(self, account_id: str, session_data: bytes) -> str: ...

    def load_session(self, reference: str) -> bytes: ...

    def delete_session(self, reference: str) -> None: ...


class MockSessionVault:
    def __init__(self) -> None:
        self._sessions: dict[str, bytes] = {}

    def store_session(self, account_id: str, session_data: bytes) -> str:
        reference = f"mock:{account_id}"
        self._sessions[reference] = bytes(session_data)
        return reference

    def load_session(self, reference: str) -> bytes:
        return self._sessions[reference]

    def delete_session(self, reference: str) -> None:
        self._sessions.pop(reference, None)


class EncryptedLocalSessionVault:
    """Development vault; only encrypted bytes are written to disk.

    The Fernet key is supplied by `TELEGRAM_SESSION_ENCRYPTION_KEY`; no key or
    session content is returned by the HTTP API or written to application logs.
    """

    def __init__(self, key: str | bytes | None = None, root: str | Path = ".telegram_sessions") -> None:
        raw_key = key or os.getenv("TELEGRAM_SESSION_ENCRYPTION_KEY")
        if not raw_key:
            raise RuntimeError("TELEGRAM_SESSION_ENCRYPTION_KEY is required for EncryptedLocalSessionVault")
        self._fernet = Fernet(raw_key.encode() if isinstance(raw_key, str) else raw_key)
        self._root = Path(root)
        self._root.mkdir(mode=0o700, parents=True, exist_ok=True)

    def _path(self, reference: str) -> Path:
        digest = hashlib.sha256(reference.encode()).hexdigest()
        return self._root / f"{digest}.session"

    def store_session(self, account_id: str, session_data: bytes) -> str:
        reference = f"local:{account_id}"
        path = self._path(reference)
        path.write_bytes(self._fernet.encrypt(bytes(session_data)))
        path.chmod(0o600)
        return reference

    def load_session(self, reference: str) -> bytes:
        return self._fernet.decrypt(self._path(reference).read_bytes())

    def delete_session(self, reference: str) -> None:
        self._path(reference).unlink(missing_ok=True)
