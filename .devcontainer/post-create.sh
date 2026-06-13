#!/usr/bin/env bash
set -euo pipefail

workspace="${1:?workspace path is required}"

if [[ ! -d "${workspace}" || ! -w "${workspace}" ]]; then
    echo "${workspace} must be a writable workspace mount." >&2
    exit 1
fi

git config --global --add safe.directory "${workspace}"

if [[ ! -r /home/vscode/.codex || ! -w /home/vscode/.codex ]]; then
    echo "/home/vscode/.codex must be readable and writable by the vscode user." >&2
    exit 1
fi

if [[ -f "${workspace}/pyproject.toml" ]]; then
    cd "${workspace}"
    uv sync --all-extras --dev
fi
