from __future__ import annotations

import re
import unicodedata

from ..models import NormalizedSignal, RawSignal

_CONTACT_PATTERNS = {
    "PHONE": re.compile(r"(?<!\d)(?:\+?7|8)[\s()\-\d]{9,}(?!\d)"),
    "EMAIL": re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b"),
    "TELEGRAM_HANDLE": re.compile(r"(?<!\w)@[A-Za-z0-9_]{4,}"),
}


def _repair_mojibake(value: str) -> str:
    """Decode UTF-8 text that was accidentally interpreted as Windows-1251."""
    try:
        repaired = value.encode("cp1251").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return value
    return repaired if repaired.count("Р") < value.count("Р") else value


def normalize_signal(signal: RawSignal) -> NormalizedSignal:
    redactions: list[str] = []
    text = _repair_mojibake(unicodedata.normalize("NFKC", f"{signal.title}\n{signal.text}"))
    for name, pattern in _CONTACT_PATTERNS.items():
        text, count = pattern.subn(f"[{name}_REDACTED]", text)
        if count:
            redactions.append(name)
    text = re.sub(r"\s+", " ", text).strip()
    title = re.sub(r"\s+", " ", _repair_mojibake(unicodedata.normalize("NFKC", signal.title))).strip()
    return NormalizedSignal(
        raw_signal=signal,
        canonical_text=text.casefold(),
        title=title,
        text_for_analysis=text,
        redactions=tuple(redactions),
        source_scope=str(signal.metadata.get("source_scope", "PUBLIC_PAGE_CAPTURE")),
    )
