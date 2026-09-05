from __future__ import annotations

import hashlib
import re
import unicodedata
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from ..models import NormalizedSignal


_TRACKING_QUERY_KEYS = {"fbclid", "gclid", "msclkid", "yclid"}
_STOPWORDS = {
    "\u043d\u0443\u0436\u0435\u043d", "\u043d\u0443\u0436\u043d\u0430", "\u043d\u0443\u0436\u043d\u043e", "\u043d\u0443\u0436\u043d\u044b\u0439",
    "\u0441\u0430\u0439\u0442", "\u0441\u0434\u0435\u043b\u0430\u0442\u044c", "\u0440\u0430\u0437\u0440\u0430\u0431\u043e\u0442\u0430\u0442\u044c", "\u043d\u0435\u043e\u0431\u0445\u043e\u0434\u0438\u043c\u043e", "\u0442\u0440\u0435\u0431\u0443\u0435\u0442\u0441\u044f",
}


def classify_duplicate(signal: NormalizedSignal, prior: list[NormalizedSignal]) -> tuple[str, float]:
    tokens = _tokens(signal.canonical_text)
    for other in prior:
        if canonical_url(signal.raw_signal.source_url) == canonical_url(other.raw_signal.source_url):
            return "EXACT_DUPLICATE", 1.0
        other_tokens = _tokens(other.canonical_text)
        if tokens and tokens == other_tokens:
            return "EXACT_DUPLICATE", 1.0
        if tokens and other_tokens:
            similarity = len(tokens & other_tokens) / max(1, len(tokens | other_tokens))
            if similarity >= 0.82:
                return "LIKELY_DUPLICATE", round(similarity, 4)
            if similarity >= 0.58 and signal.raw_signal.source != other.raw_signal.source:
                return "SAME_DEMAND_DIFFERENT_SOURCE", round(similarity, 4)
    return "UNRELATED", 0.0


def canonical_url(value: str) -> str:
    """Normalize public URLs so tracking parameters do not create new leads."""
    parsed = urlsplit(value.strip())
    if not parsed.scheme or not parsed.netloc:
        return value.strip().rstrip("/")
    query = [
        (key, item)
        for key, item in parse_qsl(parsed.query, keep_blank_values=True)
        if not key.casefold().startswith("utm_") and key.casefold() not in _TRACKING_QUERY_KEYS
    ]
    path = parsed.path.rstrip("/") or "/"
    return urlunsplit((parsed.scheme.casefold(), parsed.netloc.casefold(), path, urlencode(sorted(query)), ""))


def content_fingerprint(text: str) -> str:
    """Stable fingerprint for exact demand text independent of punctuation/case."""
    normalized = " ".join(sorted(_tokens(text)))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest() if normalized else ""


def _tokens(text: str) -> set[str]:
    normalized = unicodedata.normalize("NFKC", text).casefold()
    return {
        token
        for token in re.findall(r"[^\W_]{4,}", normalized, flags=re.UNICODE)
        if token not in _STOPWORDS
    }
