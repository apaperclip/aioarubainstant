# aioarubainstant

`aioarubainstant` is a typed asynchronous Python client for the monitoring API
on Aruba Instant controllers. It is designed for Home Assistant integrations
but has no Home Assistant dependency or entity logic.

Version 0.1.0 supports Python 3.14 and Aruba Instant 8.6 monitoring commands.

## Features

- HTTPS communication with `aiohttp` on port 4343 by default
- Configurable TLS certificate verification
- SID authentication, reuse, and one automatic reauthentication attempt
- Serialized controller commands to avoid overlapping CLI requests
- Caller-provided `aiohttp.ClientSession` support
- Async context-manager and explicit cleanup APIs
- Typed immutable cluster, access-point, client, and snapshot models
- Header-derived table parsing tolerant of reordered and additional columns
- Sanitized raw command output retained privately for diagnostics

The supported commands are `show aps`, `show clients`, `show client debug`,
`show summary`, and `show version`. The library never issues a per-client
`show client status <mac>` request.

## Controller setup

The REST API is disabled by default and is available only through the master AP
in a cluster. Enable it from the Aruba Instant CLI:

```text
(Instant AP)(config)# allow-rest-api
(Instant AP)(config)# end
(Instant AP)# commit-apply
```

The transport and response behavior follow the
[Aruba Instant 8.6.0.x REST API Guide](https://www.langs-world.de/Downloads/ArubaInstant/AI_8.6.0.22/Aruba%20Instant%208.6.0.x%20REST%20API%20Guide.pdf).

## Installation

```bash
python -m pip install aioarubainstant==0.1.0
```

## Usage

```python
import asyncio

from aioarubainstant import ArubaInstantClient


async def main() -> None:
    async with ArubaInstantClient(
        "192.0.2.1",
        "admin",
        "controller-password",
        verify_ssl=True,
    ) as client:
        snapshot = await client.async_get_snapshot()

    print(snapshot.cluster.name, snapshot.cluster.version)
    for access_point in snapshot.access_points:
        print(access_point.name, access_point.connected_clients)
    for wireless_client in snapshot.clients:
        print(wireless_client.hostname, wireless_client.associated_ap)


asyncio.run(main())
```

Controllers commonly use a private certificate. Prefer an `ssl.SSLContext`
that trusts the controller CA. Set `verify_ssl=False` only when certificate
verification is intentionally disabled.

For a caller-owned HTTP session:

```python
import aiohttp

from aioarubainstant import ArubaInstantClient

async with aiohttp.ClientSession() as session:
    client = ArubaInstantClient(
        "controller.example.com",
        "admin",
        "controller-password",
        session=session,
    )
    snapshot = await client.async_get_snapshot()
    await client.async_close()
```

`async_close()` logs out but never closes a caller-provided session.

## Public contract

The package exports:

- `ArubaInstantClient`
- `async_get_snapshot()`
- `ArubaInstantSnapshot`
- `ArubaCluster`
- `ArubaAccessPoint`
- `ArubaClient`

Model fields are immutable. A field is `None` when the controller did not
report it; the package does not invent placeholder values. A snapshot contains
one `ArubaCluster`, tuples of access points and clients, and private sanitized
raw output for diagnostics.

The exception hierarchy is rooted at `ArubaInstantError`:

- `ArubaInstantAuthenticationError`: login credentials were rejected
- `ArubaInstantConnectionError`: controller connection or HTTP failure
- `ArubaInstantTimeoutError`: request timeout; also a connection error
- `ArubaInstantRestDisabledError`: REST API is not enabled
- `ArubaInstantNotMasterError`: REST request was sent to a non-master AP
- `ArubaInstantSessionError`: invalid or expired SID after the allowed retry
- `ArubaInstantCommandError`: controller rejected or failed a command
- `ArubaInstantParseError`: malformed JSON or unsupported command output

Passwords and session IDs are never logged. Do not place controller, GitHub,
PyPI, or Codex credentials in this repository.

## Home Assistant

Use this exact manifest dependency for version 0.1.0:

```json
"requirements": ["aioarubainstant==0.1.0"]
```

Home Assistant can rely on immutable snapshots, stable MAC-address client
identity, AP/client association, master resolution, explicit zero-client
collections, and the exception contract above.

## Development

Open the repository in VS Code and run
`Dev Containers: Rebuild and Reopen in Container`. The container provides
Python 3.14, `uv`, Ruff, mypy, pytest, build tools, PDF inspection utilities,
and GitHub CLI.

The host `${HOME}/.codex` directory is bind-mounted to `/home/vscode/.codex`.
The `uv` cache is persisted separately in a named volume. No authentication
data is copied into the image or repository.

Run the complete local checks with:

```bash
uv sync --all-extras --dev
uv run ruff check src tests
uv run ruff format --check src tests
uv run mypy src tests
uv run pytest
uv build
uv run twine check dist/*
```

## Release publishing

GitHub releases trigger `.github/workflows/release.yml`, which builds and
validates the distributions before publishing through PyPI trusted publishing.
Configure the PyPI project with owner `apaperclip`, repository
`aioarubainstant`, workflow `release.yml`, and environment `pypi`. No PyPI token
is stored in GitHub or this repository.

## License

Apache License 2.0. See [LICENSE](LICENSE).
