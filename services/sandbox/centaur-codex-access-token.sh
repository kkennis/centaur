#!/bin/sh
set -eu

token="${CODEX_ACCESS_TOKEN:-}"
if [ -z "$token" ]; then
    echo "CODEX_ACCESS_TOKEN is not set" >&2
    exit 1
fi
if [ "$token" != "CODEX_ACCESS_TOKEN" ]; then
    echo "CODEX_ACCESS_TOKEN must be the sandbox placeholder" >&2
    exit 1
fi

printf '%s\n' "$token"
