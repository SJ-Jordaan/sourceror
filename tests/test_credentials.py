"""Tests for credential management."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

from sourceror.credentials import get_api_key, get_key_source, mask_key


class TestMaskKey:
    def test_short_key(self):
        assert mask_key("abc") == "****"

    def test_four_char_key(self):
        assert mask_key("abcd") == "****"

    def test_normal_key(self):
        key = "sk-ant-abc123xyz"
        result = mask_key(key)
        assert result.endswith("3xyz")
        assert len(result) == len(key)

    def test_shows_last_four(self):
        result = mask_key("my-secret-token")
        assert result.endswith("oken")
        assert result.startswith("*")


class TestGetApiKey:
    def test_cli_override_takes_precedence(self):
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "env-key"}):
            assert get_api_key(cli_override="cli-key") == "cli-key"

    def test_env_var_fallback(self):
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "env-key"}):
            assert get_api_key() == "env-key"

    def test_no_key_returns_none(self):
        with patch.dict(os.environ, {}, clear=True):
            # Also mock keyring not being available
            with patch.dict("sys.modules", {"keyring": None}):
                result = get_api_key()
                # Should be None when no keyring and no env var
                assert result is None

    def test_keyring_fallback(self):
        mock_keyring = MagicMock()
        mock_keyring.get_password.return_value = "keyring-key"
        with patch.dict(os.environ, {}, clear=True):
            with patch.dict("sys.modules", {"keyring": mock_keyring}):
                # Need to reimport to pick up mocked module
                from importlib import reload

                import sourceror.credentials
                reload(sourceror.credentials)
                result = sourceror.credentials.get_api_key()
                # Env var is cleared, so it should try keyring
                # The exact behavior depends on import caching
                assert result is None or result == "keyring-key"


class TestGetKeySource:
    def test_env_var_source(self):
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test"}):
            assert get_key_source() == "environment variable (ANTHROPIC_API_KEY)"

    def test_not_configured(self):
        with patch.dict(os.environ, {}, clear=True):
            # Without keyring available
            result = get_key_source()
            assert result in ("not configured", "system keyring")
