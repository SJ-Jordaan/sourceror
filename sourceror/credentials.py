"""Secure credential storage using system keyring."""

from __future__ import annotations

import os

SERVICE_NAME = "sourceror"
ANTHROPIC_KEY_NAME = "anthropic-api-key"


def get_api_key(cli_override: str | None = None) -> str | None:
    """Resolve Anthropic API key with precedence: CLI flag > env var > keyring."""
    if cli_override:
        return cli_override

    key = os.environ.get("ANTHROPIC_API_KEY")
    if key:
        return key

    try:
        import keyring

        return keyring.get_password(SERVICE_NAME, ANTHROPIC_KEY_NAME)
    except ImportError:
        return None
    except Exception:
        return None


def set_api_key(key: str) -> None:
    """Store API key in system keyring."""
    import keyring

    keyring.set_password(SERVICE_NAME, ANTHROPIC_KEY_NAME, key)


def clear_api_key() -> None:
    """Remove API key from system keyring."""
    import keyring

    try:
        keyring.delete_password(SERVICE_NAME, ANTHROPIC_KEY_NAME)
    except keyring.errors.PasswordDeleteError:
        pass


def get_key_source() -> str:
    """Return where the current API key comes from."""
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "environment variable (ANTHROPIC_API_KEY)"
    try:
        import keyring

        if keyring.get_password(SERVICE_NAME, ANTHROPIC_KEY_NAME):
            return "system keyring"
    except (ImportError, Exception):
        pass
    return "not configured"


def mask_key(key: str) -> str:
    """Mask all but last 4 characters."""
    if len(key) <= 4:
        return "****"
    return "*" * (len(key) - 4) + key[-4:]
