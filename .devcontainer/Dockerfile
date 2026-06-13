FROM mcr.microsoft.com/devcontainers/python:3-3.14-bookworm

USER root

RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install --yes --no-install-recommends \
        build-essential \
        ca-certificates \
        curl \
        git \
        jq \
        poppler-utils \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/
COPY post-create.sh /usr/local/bin/aioarubainstant-post-create

RUN chmod 0755 /usr/local/bin/aioarubainstant-post-create \
    && mkdir -p /home/vscode/.cache/uv \
    && chown -R vscode:vscode /home/vscode/.cache

USER vscode
