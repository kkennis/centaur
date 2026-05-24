from __future__ import annotations

import json
import os
import subprocess
import tomllib
from pathlib import Path


ENTRYPOINT_SH = Path(__file__).resolve().parents[2] / "sandbox" / "entrypoint.sh"
CODEX_ACCESS_TOKEN_HELPER = (
    Path(__file__).resolve().parents[2]
    / "sandbox"
    / "centaur-codex-access-token.sh"
)
REPO_ROOT = Path(__file__).resolve().parents[3]
HARNESS_CODEX_CONFIG = REPO_ROOT / "harness" / "codex" / "config.toml"


def test_harness_codex_config_has_no_top_level_model_provider() -> None:
    """entrypoint.sh's access-token setup blindly prepends
    `model_provider = "centaur_codex_access_token"` to the harness config.
    If the harness config ever gains a top-level `model_provider` of its
    own, the file would end up with two and Codex would fail to parse it.
    Pin the invariant here so any future commit that breaks it fails CI
    instead of the sandbox at runtime."""
    parsed = tomllib.loads(HARNESS_CODEX_CONFIG.read_text())
    assert "model_provider" not in parsed, (
        "harness/codex/config.toml must not declare a top-level "
        "model_provider; entrypoint.sh prepends one in access-token mode."
    )


HARNESS_CODEX_ACCESS_TOKEN_PROVIDER = (
    REPO_ROOT / "harness" / "codex" / "access-token-provider.toml"
)


def _write_codex_harness_config(home: Path) -> Path:
    harness_dir = home / "harness"
    codex_dir = harness_dir / "codex"
    codex_dir.mkdir(parents=True)
    # Mirror the real harness layout: entrypoint expects the access-token
    # provider snippet alongside config.toml in $CENTAUR_HARNESS_CONFIG_DIR.
    (codex_dir / "access-token-provider.toml").write_text(
        HARNESS_CODEX_ACCESS_TOKEN_PROVIDER.read_text()
    )
    (codex_dir / "config.toml").write_text(
        "\n".join(
            [
                'model = "gpt-5.5"',
                'model_reasoning_effort = "low"',
                'plan_mode_reasoning_effort = "high"',
                'approval_policy = "on-request"',
                'approvals_reviewer = "user"',
                'web_search = "live"',
                'personality = "pragmatic"',
                'sandbox_mode = "workspace-write"',
                "check_for_update_on_startup = true",
                "suppress_unstable_features_warning = true",
                'service_tier = "fast"',
                "",
                "[tools]",
                "view_image = true",
                "",
                "[features]",
                "goals = true",
                "memories = true",
                "code_mode = true",
                "hooks = true",
                "browser_use = true",
                "computer_use = true",
                "enable_fanout = true",
                "runtime_metrics = true",
                "",
                "[features.multi_agent_v2]",
                "enabled = true",
                "max_concurrent_threads_per_session = 6",
                "",
                "[agents]",
                "max_depth = 2",
                "job_max_runtime_seconds = 1800",
                "",
            ]
        )
    )
    return harness_dir


def _write_fake_codex(bin_dir: Path) -> None:
    bin_dir.mkdir(parents=True)
    codex = bin_dir / "codex"
    codex.write_text(
        "\n".join(
            [
                "#!/bin/sh",
                "printf '%s\\n' \"$*\" > \"$CODEX_LOGIN_ARGS_FILE\"",
                "cat > \"$CODEX_LOGIN_STDIN_FILE\"",
                "",
            ]
        )
    )
    codex.chmod(0o755)


def test_sandbox_entrypoint_bootstraps_mock_google_adc(tmp_path: Path) -> None:
    home = tmp_path / "home"
    (home / ".config" / "amp").mkdir(parents=True)
    harness_dir = _write_codex_harness_config(home)

    result = subprocess.run(
        [
            "bash",
            str(ENTRYPOINT_SH),
            "sh",
            "-lc",
            'printf \'%s\n\' "$GOOGLE_APPLICATION_CREDENTIALS" && cat "$GOOGLE_APPLICATION_CREDENTIALS"',
        ],
        check=False,
        capture_output=True,
        text=True,
        env={
            "HOME": str(home),
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "CENTAUR_HARNESS_CONFIG_DIR": str(harness_dir),
        },
    )

    assert result.returncode == 0, result.stderr or result.stdout
    adc_path, adc_json = result.stdout.split("\n", 1)
    assert adc_path == str(
        home / ".config" / "gcloud" / "application_default_credentials.json"
    )
    assert Path(adc_path).is_file()
    adc = json.loads(adc_json)
    assert adc == {
        "type": "service_account",
        "project_id": "centaur-sandbox",
        "private_key_id": "0000000000000000000000000000000000000000",
        "private_key": adc["private_key"],
        "client_email": "mock@creds.com",
        "client_id": "100000000000000000000",
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
        "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/mock%40creds.com",
        "universe_domain": "googleapis.com",
    }
    assert adc["private_key"].startswith("-----BEGIN PRIVATE KEY-----\n")
    assert adc["private_key"].endswith("-----END PRIVATE KEY-----\n")

    codex_config = (home / ".codex" / "config.toml").read_text()
    assert 'model = "gpt-5.5"' in codex_config
    assert 'model_reasoning_effort = "low"' in codex_config
    assert 'plan_mode_reasoning_effort = "high"' in codex_config
    assert 'approval_policy = "on-request"' in codex_config
    assert 'sandbox_mode = "workspace-write"' in codex_config
    assert 'service_tier = "fast"' in codex_config
    assert "max_concurrent_threads_per_session = 6" in codex_config


def test_sandbox_entrypoint_installs_codex_harness_config(tmp_path: Path) -> None:
    home = tmp_path / "home"
    harness_dir = _write_codex_harness_config(home)

    result = subprocess.run(
        [
            "bash",
            str(ENTRYPOINT_SH),
            "sh",
            "-lc",
            'cat "$HOME/.codex/config.toml"',
        ],
        check=False,
        capture_output=True,
        text=True,
        env={
            "HOME": str(home),
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "CENTAUR_HARNESS_CONFIG_DIR": str(harness_dir),
        },
    )

    assert result.returncode == 0, result.stderr or result.stdout
    assert result.stdout == (harness_dir / "codex" / "config.toml").read_text()


def test_sandbox_entrypoint_appends_codex_laminar_otel_config(tmp_path: Path) -> None:
    home = tmp_path / "home"
    harness_dir = _write_codex_harness_config(home)

    result = subprocess.run(
        [
            "bash",
            str(ENTRYPOINT_SH),
            "sh",
            "-lc",
            'cat "$HOME/.codex/config.toml"',
        ],
        check=False,
        capture_output=True,
        text=True,
        env={
            "HOME": str(home),
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "CENTAUR_HARNESS_CONFIG_DIR": str(harness_dir),
            "CENTAUR_THREAD_KEY": "slack:C123:1700000000.000100",
            "CENTAUR_TRACE_ID": "00000000-0000-0000-0000-000000000123",
            "CODEX_OTEL_ENVIRONMENT": "staging",
            "LMNR_BASE_URL": "http://stg-laminar-app-server.stg-laminar.svc.cluster.local:8000",
            "LMNR_PROJECT_API_KEY": "lmnr-key",
        },
    )

    assert result.returncode == 0, result.stderr or result.stdout
    assert result.stdout.startswith((harness_dir / "codex" / "config.toml").read_text())
    parsed = tomllib.loads(result.stdout)
    assert "exporter" not in parsed["otel"]
    assert (
        parsed["otel"]["trace_exporter"]["otlp-http"]["endpoint"]
        == "http://stg-laminar-app-server.stg-laminar.svc.cluster.local:8000/v1/traces"
    )
    assert "\nexporter = { otlp-http = {" not in result.stdout
    assert "trace_exporter = { otlp-http = {" in result.stdout
    assert (
        'endpoint = "http://stg-laminar-app-server.stg-laminar.svc.cluster.local:8000/v1/traces"'
        in result.stdout
    )
    assert '"x-trace-id" = "00000000-0000-0000-0000-000000000123"' in result.stdout
    assert '"x-centaur-thread-key" = "slack:C123:1700000000.000100"' in result.stdout
    assert '"authorization" = "Bearer lmnr-key"' in result.stdout
    assert 'environment = "staging"' in result.stdout


def test_sandbox_entrypoint_configures_codex_access_token_provider(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    harness_dir = _write_codex_harness_config(home)
    fake_bin = tmp_path / "bin"
    _write_fake_codex(fake_bin)
    args_file = tmp_path / "codex-args"
    stdin_file = tmp_path / "codex-stdin"

    result = subprocess.run(
        [
            "bash",
            str(ENTRYPOINT_SH),
            "sh",
            "-lc",
            'cat "$HOME/.codex/config.toml"',
        ],
        check=False,
        capture_output=True,
        text=True,
        env={
            "HOME": str(home),
            "PATH": f"{fake_bin}:{os.environ.get('PATH', '/usr/bin:/bin')}",
            "CENTAUR_HARNESS_CONFIG_DIR": str(harness_dir),
            # The API stamps the literal placeholder + the CODEX_AUTH_MODE
            # signal. Entrypoint requires both to flip provider config.
            "CODEX_ACCESS_TOKEN": "CODEX_ACCESS_TOKEN",
            "CODEX_AUTH_MODE": "access_token",
            "CODEX_API_KEY": "codex-api-key",
            "OPENAI_API_KEY": "openai-api-key",
            "CODEX_LOGIN_ARGS_FILE": str(args_file),
            "CODEX_LOGIN_STDIN_FILE": str(stdin_file),
        },
    )

    assert result.returncode == 0, result.stderr or result.stdout
    assert not args_file.exists()
    assert not stdin_file.exists()
    parsed = tomllib.loads(result.stdout)
    assert parsed["model_provider"] == "centaur_codex_access_token"
    provider = parsed["model_providers"]["centaur_codex_access_token"]
    assert provider["name"] == "OpenAI via Centaur Codex access token"
    assert provider["base_url"] == "https://chatgpt.com/backend-api/codex"
    assert provider["wire_api"] == "responses"
    assert provider["supports_websockets"] is False
    assert provider["auth"] == {
        "command": "/usr/local/bin/centaur-codex-access-token",
        "timeout_ms": 5000,
        "refresh_interval_ms": 0,
    }


def test_sandbox_entrypoint_rejects_non_placeholder_access_token(
    tmp_path: Path,
) -> None:
    """If something injects a real-looking CODEX_ACCESS_TOKEN into the sandbox
    while CODEX_AUTH_MODE=access_token, the entrypoint must refuse to start —
    the sandbox should only ever see the placeholder string."""
    home = tmp_path / "home"
    harness_dir = _write_codex_harness_config(home)
    fake_bin = tmp_path / "bin"
    _write_fake_codex(fake_bin)

    result = subprocess.run(
        [
            "bash",
            str(ENTRYPOINT_SH),
            "sh",
            "-lc",
            "true",
        ],
        check=False,
        capture_output=True,
        text=True,
        env={
            "HOME": str(home),
            "PATH": f"{fake_bin}:{os.environ.get('PATH', '/usr/bin:/bin')}",
            "CENTAUR_HARNESS_CONFIG_DIR": str(harness_dir),
            "CODEX_ACCESS_TOKEN": "sk-real-leaked-token",
            "CODEX_AUTH_MODE": "access_token",
            "CODEX_LOGIN_ARGS_FILE": str(tmp_path / "codex-args"),
            "CODEX_LOGIN_STDIN_FILE": str(tmp_path / "codex-stdin"),
        },
    )

    assert result.returncode != 0
    assert "sandbox placeholder" in result.stderr


def test_sandbox_entrypoint_ignores_access_token_without_mode(
    tmp_path: Path,
) -> None:
    """A CODEX_ACCESS_TOKEN leaked into the sandbox env without CODEX_AUTH_MODE
    must NOT flip Codex to access-token mode. The legacy api-key path stays
    active."""
    home = tmp_path / "home"
    harness_dir = _write_codex_harness_config(home)
    fake_bin = tmp_path / "bin"
    _write_fake_codex(fake_bin)
    args_file = tmp_path / "codex-args"
    stdin_file = tmp_path / "codex-stdin"

    result = subprocess.run(
        [
            "bash",
            str(ENTRYPOINT_SH),
            "sh",
            "-lc",
            'cat "$HOME/.codex/config.toml"',
        ],
        check=False,
        capture_output=True,
        text=True,
        env={
            "HOME": str(home),
            "PATH": f"{fake_bin}:{os.environ.get('PATH', '/usr/bin:/bin')}",
            "CENTAUR_HARNESS_CONFIG_DIR": str(harness_dir),
            "CODEX_ACCESS_TOKEN": "CODEX_ACCESS_TOKEN",
            # No CODEX_AUTH_MODE set — entrypoint must NOT switch to access_token.
            "OPENAI_API_KEY": "openai-api-key",
            "CODEX_LOGIN_ARGS_FILE": str(args_file),
            "CODEX_LOGIN_STDIN_FILE": str(stdin_file),
        },
    )

    assert result.returncode == 0, result.stderr or result.stdout
    parsed = tomllib.loads(result.stdout)
    assert parsed.get("model_provider") != "centaur_codex_access_token"
    # api-key login fallback still ran with the OPENAI_API_KEY value.
    assert stdin_file.read_text() == "openai-api-key\n"


def test_sandbox_entrypoint_falls_back_to_codex_api_key_login(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    harness_dir = _write_codex_harness_config(home)
    fake_bin = tmp_path / "bin"
    _write_fake_codex(fake_bin)
    args_file = tmp_path / "codex-args"
    stdin_file = tmp_path / "codex-stdin"

    result = subprocess.run(
        [
            "bash",
            str(ENTRYPOINT_SH),
            "sh",
            "-lc",
            "true",
        ],
        check=False,
        capture_output=True,
        text=True,
        env={
            "HOME": str(home),
            "PATH": f"{fake_bin}:{os.environ.get('PATH', '/usr/bin:/bin')}",
            "CENTAUR_HARNESS_CONFIG_DIR": str(harness_dir),
            "CODEX_API_KEY": "codex-api-key",
            "OPENAI_API_KEY": "openai-api-key",
            "CODEX_LOGIN_ARGS_FILE": str(args_file),
            "CODEX_LOGIN_STDIN_FILE": str(stdin_file),
        },
    )

    assert result.returncode == 0, result.stderr or result.stdout
    assert args_file.read_text().strip() == "login --with-api-key"
    # Entrypoint sends the key newline-terminated to codex login.
    assert stdin_file.read_text() == "codex-api-key\n"


def test_codex_access_token_helper_prints_placeholder() -> None:
    result = subprocess.run(
        ["sh", str(CODEX_ACCESS_TOKEN_HELPER)],
        check=False,
        capture_output=True,
        text=True,
        env={"CODEX_ACCESS_TOKEN": "CODEX_ACCESS_TOKEN"},
    )

    assert result.returncode == 0, result.stderr or result.stdout
    assert result.stdout == "CODEX_ACCESS_TOKEN\n"


def test_codex_access_token_helper_requires_token() -> None:
    result = subprocess.run(
        ["sh", str(CODEX_ACCESS_TOKEN_HELPER)],
        check=False,
        capture_output=True,
        text=True,
        env={},
    )

    assert result.returncode == 1
    assert result.stderr == "CODEX_ACCESS_TOKEN is not set\n"


def test_codex_access_token_helper_rejects_raw_token() -> None:
    result = subprocess.run(
        ["sh", str(CODEX_ACCESS_TOKEN_HELPER)],
        check=False,
        capture_output=True,
        text=True,
        env={"CODEX_ACCESS_TOKEN": "real-token"},
    )

    assert result.returncode == 1
    assert result.stderr == "CODEX_ACCESS_TOKEN must be the sandbox placeholder\n"
