# aioarubainstant

`aioarubainstant` is a typed asynchronous Python client for the monitoring API
on Aruba Instant controllers. It is designed for Home Assistant integrations
but has no Home Assistant dependency or entity logic.

Version 0.1.4 supports Python 3.14 and Aruba Instant 8.6 monitoring commands.

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

The supported commands are `show aps`, `show client debug`, `show summary`, and
`show version`. The library never issues a per-client
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
Command output formats follow the official
[Instant AOS-8.x CLI Reference Guide](https://arubanetworking.hpe.com/techdocs/Aruba-Instant-8.x-Books/Aruba-Instant-8.x-CLI-Guide.pdf),
including its Instant AOS-8.6 command history and examples.

## Installation

```bash
python -m pip install aioarubainstant==0.1.4
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

Some Aruba Instant firmware emits a malformed response header that aiohttp
rejects when `PYTHONASYNCIODEBUG` enables strict response parsing. A client
using its internally owned HTTP session scopes Aruba-compatible response
parsing to that controller connection without disabling asyncio debug globally.
This compatibility behavior is included in version 0.1.1 and later.

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
Caller-provided sessions also retain their own connector and response-parser
behavior; they do not use the Aruba-specific compatibility connector.

## Public contract

The package exports:

- `ArubaInstantClient`
- `async_get_snapshot()`
- `ArubaInstantSnapshot`
- `ArubaCluster`
- `ArubaAccessPoint`
- `ArubaClient`

See [Package Usage](docs/USAGE.md) for the complete model, exception, TLS, and
integration contract.

Model fields are immutable. A field is `None` when the controller did not
report it; the package does not invent placeholder values. A snapshot contains
one `ArubaCluster`, tuples of access points and clients, and private sanitized
raw output for diagnostics.

Client counts are never derived by counting parsed records. The cluster total
comes from the controller-reported value in `show summary`, and each AP's count
comes from the `Clients` field in `show aps`. Parsed `show client debug` rows
provide client details only.

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

Use this exact manifest dependency for version 0.1.4:

```json
"requirements": ["aioarubainstant==0.1.4"]
```

Home Assistant can rely on immutable snapshots, stable MAC-address client
identity, AP/client association, master resolution, explicit zero-client
collections, and the exception contract above.
Version 0.1.4 allows Home Assistant environments pinned to
`aiohttp==3.13.5`.

## Development

Open the repository in VS Code and run
`Dev Containers: Rebuild and Reopen in Container`. The container provides
Python 3.14, `uv`, Ruff, mypy, pytest, build tools, PDF inspection utilities,
and GitHub CLI.

The host `${HOME}/.codex` directory is bind-mounted to `/home/vscode/.codex`.
The `uv` cache is persisted separately in a named volume. No authentication
data is copied into the image or repository.

Maintainers and coding agents should read [Repository Guidance](AGENTS.md) and
[Project Notes](docs/PROJECT_NOTES.md) before changing command selection,
parsing, count provenance, or release automation.

For the planned Home Assistant Core migration, use the reusable
[Home Assistant Codex goal prompt](docs/HOME_ASSISTANT_CODEX_PROMPT.md).

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

### Real-controller smoke test

The real-controller test is a separate local developer tool. It is not run by
CI or by the release workflow. Invoke it explicitly when an Aruba Instant AP is
available:

```bash
uv run python scripts/check_real_ap.py controller.example.com admin
```

The script prompts for the controller password without placing it in shell
history or process arguments. TLS certificate verification is enabled by
default. Use `--ca-file controller-ca.pem` for a private controller CA, or
`--insecure` only for an intentional local test. By default it validates each
supported command independently, validates the combined snapshot, and prints a
privacy-safe structural report without raw output, passwords, or session IDs.

To validate one command in isolation:

```bash
uv run python scripts/check_real_ap.py controller.example.com admin --insecure \
  --validate-command "show client debug"
```

Focused command validation prints that command's raw output before the
validation result. The default all-command validation remains privacy-safe and
does not print raw output.

To print only the controller's raw `show summary` output for manual inspection:

```bash
uv run python scripts/check_real_ap.py controller.example.com admin --insecure --show-summary
```

Use `--show-command` to inspect another supported command, for example:

```bash
uv run python scripts/check_real_ap.py controller.example.com admin --insecure \
  --show-command "show client debug"
```

Raw command output may contain controller names, network addresses, client MAC
addresses, or other private data. Do not publish it without reviewing and
redacting those values.

## Release publishing

GitHub releases trigger `.github/workflows/release.yml`, which builds and
validates the distributions before publishing through PyPI trusted publishing.
The trusted publisher is configured for owner `apaperclip`, repository
`aioarubainstant`, workflow `release.yml`, and environment `pypi`. No PyPI
token is stored in GitHub or this repository.

Version 0.1.4 is available from
[PyPI](https://pypi.org/project/aioarubainstant/0.1.4/) and the
[GitHub release](https://github.com/apaperclip/aioarubainstant/releases/tag/v0.1.4).

## License

Apache License 2.0. See [LICENSE](LICENSE).
