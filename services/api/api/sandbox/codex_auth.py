"""Codex auth-mode resolution for the sandbox harness.

The API picks one of two Codex auth paths at startup based on the
``CODEX_AUTH_MODE`` env var, freezes the choice for the process lifetime,
and stamps a placeholder + selector pair into each sandbox's env. The
sandbox-side ``entrypoint.sh`` cross-checks the selector before flipping
Codex's provider config.
"""

from __future__ import annotations

import os
from enum import Enum

import structlog

log = structlog.get_logger()


class CodexAuthMode(str, Enum):
    """Which Codex auth path the harness uses.

    ``api_key`` — Codex talks to ``api.openai.com`` with an
    ``OPENAI_API_KEY`` placeholder that iron-proxy rewrites.
    ``access_token`` — Codex talks to ``chatgpt.com/backend-api/codex`` with
    a ``CODEX_ACCESS_TOKEN`` placeholder; iron-proxy mints and injects an
    OpenAI ``AgentAssertion`` per request.
    """

    API_KEY = "api_key"
    ACCESS_TOKEN = "access_token"


class CodexAuthConfigError(RuntimeError):
    """``CODEX_AUTH_MODE`` is invalid or names an unconfigured credential."""


# Frozen by the API lifespan after resolve_codex_auth_mode() succeeds at
# startup. None until then — tests reset this via the conftest autouse
# fixture and rely on resolve_codex_auth_mode() being called live. Mirrors
# the module-level state pattern in api.warm_pool.
_active_mode: CodexAuthMode | None = None


def resolve_codex_auth_mode() -> CodexAuthMode:
    """Return the active Codex auth mode for this deployment.

    Reads ``CODEX_AUTH_MODE`` from the API process env. Unset defaults to
    :data:`CodexAuthMode.API_KEY`. The selected mode determines which
    sandbox placeholder wiring is active:

    * ``api_key`` — ``OPENAI_API_KEY`` placeholder path.
    * ``access_token`` — ChatGPT/Codex account-auth placeholder path.

    Credential presence is only validated when ``CODEX_AUTH_MODE`` is set
    explicitly — the default does not require ``OPENAI_API_KEY`` because
    many deployments use Claude or Amp and never touch Codex. An explicit
    selector is treated as an opt-in to fail-fast on a misconfigured
    credential. 1Password-backed proxy secret resolution skips the presence
    check either way because real credentials don't live in the API process.

    Raises :class:`CodexAuthConfigError` only when the selector is set to an
    unknown value or when an explicit selector names a missing credential
    under env-source proxy resolution.
    """
    raw = (os.getenv("CODEX_AUTH_MODE") or "").strip().lower()
    if not raw:
        return CodexAuthMode.API_KEY
    try:
        mode = CodexAuthMode(raw)
    except ValueError:
        raise CodexAuthConfigError(
            f"CODEX_AUTH_MODE={raw!r} is invalid; expected "
            f"'{CodexAuthMode.ACCESS_TOKEN.value}' or "
            f"'{CodexAuthMode.API_KEY.value}'"
        ) from None

    secret_source = (
        os.getenv("FIREWALL_MANAGER_SECRET_SOURCE") or "env"
    ).strip().lower()
    if secret_source == "env":
        if mode is CodexAuthMode.ACCESS_TOKEN:
            if not (os.getenv("CODEX_ACCESS_TOKEN") or "").strip():
                raise CodexAuthConfigError(
                    "CODEX_AUTH_MODE=access_token requires CODEX_ACCESS_TOKEN "
                    "to be set when FIREWALL_MANAGER_SECRET_SOURCE=env"
                )
        elif not (os.getenv("OPENAI_API_KEY") or "").strip():
            raise CodexAuthConfigError(
                "CODEX_AUTH_MODE=api_key requires OPENAI_API_KEY to be set "
                "when FIREWALL_MANAGER_SECRET_SOURCE=env"
            )
    return mode


def codex_auth_mode() -> CodexAuthMode:
    """Return the mode frozen at startup, else resolve once.

    Per-spawn callers (``container_env``, warm pool) read through this so
    transient env drift after startup can't raise
    :class:`CodexAuthConfigError` into a request handler. Tests that haven't
    set ``_active_mode`` fall through to live resolution.
    """
    if _active_mode is not None:
        return _active_mode
    return resolve_codex_auth_mode()


def bootstrap_codex_auth_mode() -> CodexAuthMode:
    """Resolve, freeze, and log the Codex auth mode for this process.

    Call this once during application startup (FastAPI lifespan). Raises
    :class:`CodexAuthConfigError` on invalid configuration, which aborts
    startup before any other subsystem comes up.
    """
    global _active_mode
    mode = resolve_codex_auth_mode()
    _active_mode = mode
    codex_access_token_present = bool((os.getenv("CODEX_ACCESS_TOKEN") or "").strip())
    openai_api_key_present = bool((os.getenv("OPENAI_API_KEY") or "").strip())
    log.info(
        "codex_auth_mode_resolved",
        mode=mode.value,
        codex_access_token_present=codex_access_token_present,
        openai_api_key_present=openai_api_key_present,
        selector=(os.getenv("CODEX_AUTH_MODE") or "").strip().lower() or None,
        api_key_ignored_for_codex=(
            mode is CodexAuthMode.ACCESS_TOKEN and openai_api_key_present
        ),
        codex_access_token_ignored=(
            mode is CodexAuthMode.API_KEY and codex_access_token_present
        ),
    )
    return mode
