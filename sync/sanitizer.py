"""
AI Supervisor — Data Boundary & Secret Sanitizer
Strictly sanitizes domain payloads before synchronization.
Guarantees that credentials, tokens, private keys, environment secrets,
and host-local absolute paths NEVER leave the local machine.
"""

import os
import re
from typing import Any, Dict, List, Set, Union

# Sensitive key substrings that indicate secrets
SENSITIVE_KEY_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key)"),
    re.compile(r"(?i)(?:^|[_-])key(?:$|[_-])"),
    re.compile(r"(?i)(?:^|[_-])token(?:$|[_-])"),
    re.compile(r"(?i)(access[_-]?token)"),
    re.compile(r"(?i)(refresh[_-]?token)"),
    re.compile(r"(?i)(auth[_-]?token)"),
    re.compile(r"(?i)(bearer)"),
    re.compile(r"(?i)(secret)"),
    re.compile(r"(?i)(password)"),
    re.compile(r"(?i)(passwd)"),
    re.compile(r"(?i)(credential)"),
    re.compile(r"(?i)(private[_-]?key)"),
    re.compile(r"(?i)(ssh[_-]?key)"),
    re.compile(r"(?i)(jwt)"),
    re.compile(r"(?i)(authorization)"),
    re.compile(r"(?i)(env[_-]?vars?)"),
    re.compile(r"(?i)(dotenv)"),
]

# Regex patterns for sensitive values
SENSITIVE_VALUE_PATTERNS = [
    # Private keys
    re.compile(r"-----BEGIN\s+(?:RSA|DSA|EC|OPENSSH|PGP)?\s*PRIVATE\s+KEY[^-]*-----", re.DOTALL),
    # Common API key formats (OpenAI, Anthropic, etc. sk-ant-..., sk-...)
    re.compile(r"\b(?:sk|pk)[-_][a-zA-Z0-9_-]{16,}\b"),
    re.compile(r"\bgh[pousr]_[a-zA-Z0-9]{36}\b"),
    re.compile(r"\bAIza[0-9A-Za-z-_]{35}\b"),
    # JWTs (header.payload.signature)
    re.compile(r"\beyJ[a-zA-Z0-9_-]+\.eyJ[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+\b"),
    # AWS access key ID
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    # Basic Authorization / Bearer tokens
    re.compile(r"(?i)bearer\s+[a-zA-Z0-9_\-\.]{16,}"),
]

# Windows and POSIX absolute path patterns (supports spaces in directories e.g. 'AI Supervisior')
WIN_ABS_PATH_PATTERN = re.compile(r"\b[a-zA-Z]:\\(?:[^\"\'\n\r<>|*?\\/]+\\)+[^\"\'\n\r<>|*?\\/\s]+", re.IGNORECASE)
POSIX_ABS_PATH_PATTERN = re.compile(r"(?:^|[\s\"'])(\/(?:Users|home|root|var|etc|usr|opt|tmp)\/(?:[^\"\'\n\r<>|*?\\/]+\/)*[^\"\'\n\r<>|*?\\/\s]*)")


def is_sensitive_key(key: str) -> bool:
    """Checks whether a dictionary key name indicates sensitive credential data."""
    for pattern in SENSITIVE_KEY_PATTERNS:
        if pattern.search(key):
            return True
    return False


def sanitize_string_value(val: str) -> str:
    """Scrubs known secret patterns and absolute host filesystem paths from string."""
    cleaned = val

    # 1. Redact explicit secret patterns
    for pattern in SENSITIVE_VALUE_PATTERNS:
        cleaned = pattern.sub("[REDACTED_SECRET]", cleaned)

    # 2. Scrub Windows absolute paths (e.g. C:\Users\Moiz\Projects\...)
    def _scrub_win_path(match):
        full_path = match.group(0)
        parts = full_path.replace("\\", "/").split("/")
        # Keep relative filename if possible
        return f"[local_path:/{parts[-1]}]" if parts else "[local_path]"

    cleaned = WIN_ABS_PATH_PATTERN.sub(_scrub_win_path, cleaned)

    # 3. Scrub POSIX absolute paths (e.g. /home/user/project/...)
    def _scrub_posix_path(match):
        full_path = match.group(1)
        parts = full_path.split("/")
        return f"[local_path:/{parts[-1]}]" if parts else "[local_path]"

    cleaned = POSIX_ABS_PATH_PATTERN.sub(_scrub_posix_path, cleaned)

    return cleaned


def sanitize_payload(payload: Any) -> Any:
    """
    Recursively scrubs all dictionary keys and values to ensure no secrets or
    unauthorized filesystem information enter synchronization records.
    """
    if isinstance(payload, dict):
        sanitized_dict = {}
        for k, v in payload.items():
            str_key = str(k)
            # If the key itself is marked sensitive, scrub the entire value
            if is_sensitive_key(str_key):
                sanitized_dict[str_key] = "[REDACTED_CREDENTIAL]"
            else:
                sanitized_dict[str_key] = sanitize_payload(v)
        return sanitized_dict

    elif isinstance(payload, list):
        return [sanitize_payload(item) for item in payload]

    elif isinstance(payload, str):
        return sanitize_string_value(payload)

    else:
        # Primitives (int, float, bool, None) are safe
        return payload


class PayloadSanitizationError(ValueError):
    """Raised when an unscrubbed secret or credential pattern is detected in a sync payload."""
    pass


def assert_payload_is_clean(payload: Any) -> None:
    """
    Validation assertion: Raises PayloadSanitizationError if any raw secret pattern
    or unscrubbed credential key is detected.
    """
    if isinstance(payload, dict):
        for k, v in payload.items():
            str_key = str(k)
            if is_sensitive_key(str_key) and v != "[REDACTED_CREDENTIAL]":
                raise PayloadSanitizationError(f"Secret leakage detected: Key '{str_key}' was not sanitized!")
            assert_payload_is_clean(v)
    elif isinstance(payload, list):
        for item in payload:
            assert_payload_is_clean(item)
    elif isinstance(payload, str):
        for pattern in SENSITIVE_VALUE_PATTERNS:
            if pattern.search(payload):
                raise PayloadSanitizationError(f"Secret pattern detected in string value: {payload[:30]}...")
