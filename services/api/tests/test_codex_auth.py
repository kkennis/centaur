from __future__ import annotations

import pytest

import api.sandbox.codex_auth as codex_auth_module
from api.sandbox.codex_auth import (
    CodexAuthConfigError,
    CodexAuthMode,
    bootstrap_codex_auth_mode,
    codex_auth_mode,
    resolve_codex_auth_mode,
)


def _clear_codex_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in (
        "CODEX_AUTH_MODE",
        "CODEX_ACCESS_TOKEN",
        "FIREWALL_MANAGER_SECRET_SOURCE",
        "OPENAI_API_KEY",
    ):
        monkeypatch.delenv(key, raising=False)


def test_resolve_defaults_to_api_key_when_openai_api_key_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_codex_env(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    assert resolve_codex_auth_mode() == CodexAuthMode.API_KEY


def test_resolve_default_ignores_codex_access_token_presence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Presence of CODEX_ACCESS_TOKEN alone does NOT switch modes; the
    # default is still api_key, which only checks OPENAI_API_KEY.
    _clear_codex_env(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("CODEX_ACCESS_TOKEN", "tok")
    assert resolve_codex_auth_mode() == CodexAuthMode.API_KEY


def test_resolve_default_does_not_require_openai_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Non-Codex deployments (Claude-only, Amp-only) don't set OPENAI_API_KEY.
    # The default api_key mode must NOT fail-fast for them — only an
    # explicit CODEX_AUTH_MODE selector triggers credential enforcement.
    _clear_codex_env(monkeypatch)
    assert resolve_codex_auth_mode() == CodexAuthMode.API_KEY


def test_resolve_default_does_not_require_anything_with_only_access_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Setting only CODEX_ACCESS_TOKEN does not enable access_token mode and
    # does not raise; default remains api_key with no enforcement.
    _clear_codex_env(monkeypatch)
    monkeypatch.setenv("CODEX_ACCESS_TOKEN", "tok")
    assert resolve_codex_auth_mode() == CodexAuthMode.API_KEY


def test_resolve_onepassword_default_does_not_require_openai_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_codex_env(monkeypatch)
    monkeypatch.setenv("FIREWALL_MANAGER_SECRET_SOURCE", "onepassword")

    assert resolve_codex_auth_mode() == CodexAuthMode.API_KEY


def test_resolve_selector_picks_access_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_codex_env(monkeypatch)
    monkeypatch.setenv("CODEX_ACCESS_TOKEN", "tok")
    monkeypatch.setenv("CODEX_AUTH_MODE", "access_token")
    assert resolve_codex_auth_mode() == CodexAuthMode.ACCESS_TOKEN


def test_resolve_onepassword_access_token_does_not_require_token_in_api_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_codex_env(monkeypatch)
    monkeypatch.setenv("FIREWALL_MANAGER_SECRET_SOURCE", "onepassword")
    monkeypatch.setenv("CODEX_AUTH_MODE", "access_token")

    assert resolve_codex_auth_mode() == CodexAuthMode.ACCESS_TOKEN


def test_resolve_selector_access_token_ignores_openai_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # access_token mode doesn't check OPENAI_API_KEY presence either way.
    _clear_codex_env(monkeypatch)
    monkeypatch.setenv("CODEX_ACCESS_TOKEN", "tok")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("CODEX_AUTH_MODE", "access_token")
    assert resolve_codex_auth_mode() == CodexAuthMode.ACCESS_TOKEN


def test_resolve_selector_picks_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_codex_env(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("CODEX_AUTH_MODE", "api_key")
    assert resolve_codex_auth_mode() == CodexAuthMode.API_KEY


def test_resolve_selector_is_case_insensitive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_codex_env(monkeypatch)
    monkeypatch.setenv("CODEX_ACCESS_TOKEN", "tok")
    monkeypatch.setenv("CODEX_AUTH_MODE", "Access_Token")
    assert resolve_codex_auth_mode() == CodexAuthMode.ACCESS_TOKEN


def test_resolve_raises_when_selector_invalid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_codex_env(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("CODEX_AUTH_MODE", "platform")
    with pytest.raises(CodexAuthConfigError) as exc:
        resolve_codex_auth_mode()
    assert "platform" in str(exc.value)


def test_resolve_raises_when_selector_demands_missing_access_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_codex_env(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("CODEX_AUTH_MODE", "access_token")
    with pytest.raises(CodexAuthConfigError) as exc:
        resolve_codex_auth_mode()
    assert "CODEX_ACCESS_TOKEN" in str(exc.value)


def test_resolve_raises_when_selector_demands_missing_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_codex_env(monkeypatch)
    monkeypatch.setenv("CODEX_ACCESS_TOKEN", "tok")
    monkeypatch.setenv("CODEX_AUTH_MODE", "api_key")
    with pytest.raises(CodexAuthConfigError) as exc:
        resolve_codex_auth_mode()
    assert "OPENAI_API_KEY" in str(exc.value)


def test_container_env_omits_codex_placeholder_under_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Default mode is api_key. Even with CODEX_ACCESS_TOKEN set, the sandbox
    # should not see the access-token placeholder.
    from api.sandbox.config import container_env

    _clear_codex_env(monkeypatch)
    monkeypatch.delenv("AGENT_LOCAL_DEV", raising=False)
    monkeypatch.setenv("AGENT_API_URL", "http://api.internal:8000")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("CODEX_ACCESS_TOKEN", "tok")

    env = container_env("thread-key", "sandbox-id", "firewall.internal")

    assert not any(item.startswith("CODEX_ACCESS_TOKEN=") for item in env)


def test_container_env_includes_codex_placeholder_when_access_token_selected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from api.sandbox.config import container_env

    _clear_codex_env(monkeypatch)
    monkeypatch.delenv("AGENT_LOCAL_DEV", raising=False)
    monkeypatch.setenv("AGENT_API_URL", "http://api.internal:8000")
    monkeypatch.setenv("CODEX_ACCESS_TOKEN", "tok")
    monkeypatch.setenv("CODEX_AUTH_MODE", "access_token")

    env = container_env("thread-key", "sandbox-id", "firewall.internal")

    assert "CODEX_ACCESS_TOKEN=CODEX_ACCESS_TOKEN" in env
    # Sandbox-side entrypoint cross-checks CODEX_AUTH_MODE before flipping
    # provider config, so we must propagate the selector too.
    assert "CODEX_AUTH_MODE=access_token" in env


def test_codex_auth_mode_uses_frozen_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """After lifespan freezes the mode, subsequent env mutations don't
    re-trigger the resolver (so warm-pool ticks / cold spawns can't raise)."""
    _clear_codex_env(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    codex_auth_module._active_mode = CodexAuthMode.API_KEY
    try:
        # Even if env drifts to an invalid selector, the cache wins.
        monkeypatch.setenv("CODEX_AUTH_MODE", "bogus")
        assert codex_auth_mode() is CodexAuthMode.API_KEY
    finally:
        codex_auth_module._active_mode = None


def test_container_env_includes_codex_placeholder_with_onepassword_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from api.sandbox.config import container_env

    _clear_codex_env(monkeypatch)
    monkeypatch.delenv("AGENT_LOCAL_DEV", raising=False)
    monkeypatch.setenv("AGENT_API_URL", "http://api.internal:8000")
    monkeypatch.setenv("FIREWALL_MANAGER_SECRET_SOURCE", "onepassword")
    monkeypatch.setenv("CODEX_AUTH_MODE", "access_token")

    env = container_env("thread-key", "sandbox-id", "firewall.internal")

    assert "CODEX_ACCESS_TOKEN=CODEX_ACCESS_TOKEN" in env


def test_codex_auth_startup_log_path_accepts_api_key_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_codex_env(monkeypatch)
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/test")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    try:
        assert bootstrap_codex_auth_mode() is CodexAuthMode.API_KEY
        # The bootstrap freezes the cache for subsequent reads.
        assert codex_auth_module._active_mode is CodexAuthMode.API_KEY
    finally:
        codex_auth_module._active_mode = None
