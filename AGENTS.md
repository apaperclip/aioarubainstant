# Repository Guidance

This file is guidance for coding agents working on `aioarubainstant`.

## Project Scope

`aioarubainstant` is an asynchronous, typed Python library for read-only
monitoring of Aruba Instant controllers. It is designed for use by Home
Assistant integrations, but this repository must not import Home Assistant or
implement entities, coordinators, config flows, or other integration logic.

The package supports Python 3.14 and uses a `src/` layout. Preserve the existing
public API and immutable model contract unless a versioned change explicitly
requires otherwise.

## Authoritative Behavior

The snapshot uses exactly these REST CLI commands:

- `show aps`
- `show client debug`
- `show summary`
- `show version`

Do not restore `show clients` without new controller evidence and an explicit
design decision. Testing against an Aruba Instant 8.6 controller established
that `show client debug` provides the client detail fields needed by the
library.

Counts are controller-reported values, not lengths derived from parsed rows:

- Cluster client count: `show summary`
- Per-AP client count: the `Clients` field in `show aps`
- Cluster AP count: `show summary`, with the reported `show aps` count as a
  fallback

`show client debug` supplies client records only. A mismatch between a
controller-reported count and parsed records may be useful diagnostic
information, but must not silently replace the reported model value.

Never issue one `show client status <mac>` request per client.

## Parsing Rules

- Keep transport and parsing separate.
- Prefer header-derived parsing over fixed character offsets.
- Tolerate reordered columns, additional columns, blank values, CRLF, and
  harmless formatting differences.
- Preserve `None` for fields absent from controller output.
- Treat explicit zero-client output as a valid empty collection.
- Raise `ArubaInstantParseError` for malformed required output.
- Sanitize retained raw output and never log passwords or session IDs.
- Add sanitized fixtures or synthetic documentation addresses only. Never
  commit raw controller output containing real IP addresses, MAC addresses,
  hostnames, SSIDs, usernames, or other private data.

The Aruba Instant 8.6 REST API guide and the official Instant AOS-8.x CLI guide
linked from `README.md` are the protocol references. When documentation and
observed controller output differ, capture sanitized evidence and test the
chosen behavior explicitly.

## Development

Use the devcontainer when possible. Do not install project tooling on the host.

Run the full verification suite before committing:

```bash
uv sync --all-extras --dev
uv run ruff check src tests scripts
uv run ruff format --check src tests scripts
uv run mypy src tests scripts
uv run pytest
uv build
uv run twine check dist/*
```

CI performs tests, linting, typing, package builds, metadata validation, and a
clean-wheel import check. The real-controller script is intentionally local
only and must not be added to CI or release workflows.

## Releases

Publishing a GitHub release triggers `.github/workflows/release.yml`. The
workflow checks that the tag is `v<project version>`, builds the distributions,
validates and installs the wheel, and publishes through PyPI trusted
publishing using the `pypi` GitHub environment.

Before a release:

1. Update `pyproject.toml`, `src/aioarubainstant/__init__.py`, and
   `CHANGELOG.md` to the same version.
2. Ensure the release targets the final verified commit.
3. Confirm CI succeeds on that commit.
4. Review the repository for credentials, private controller output, and PII.
5. Publish the GitHub release and verify the release workflow and PyPI project.

Do not publish, yank, or replace a release unless the user explicitly requests
that external action.
