# Project Notes

This document preserves durable project context for maintainers and future
coding-agent sessions. It intentionally excludes chat transcripts, credentials,
and private controller output.

## Completed Goal

Version `0.1.0` was built as a production-quality asynchronous monitoring
library for Aruba Instant 8.6 and Home Assistant consumers.

Completed work includes:

- Python 3.14 `src/` package with Apache-2.0 licensing
- Asynchronous `aiohttp` transport over HTTPS port 4343
- SID login, reuse, logout, and one-time expired-session recovery
- Caller-owned session support and async context-manager cleanup
- Immutable typed cluster, AP, client, and snapshot models
- Header-derived and Aruba 8.6 wrapped-output parsing
- Sanitized diagnostic output retention
- Ruff, strict mypy, pytest, branch coverage, build, and Twine validation
- GitHub Actions CI and PyPI trusted publishing
- A local-only real-controller validation script
- A devcontainer with persistent host Codex state and isolated `uv` cache

## Release State

`aioarubainstant 0.1.0` was released on June 13, 2026.

- Git commit: `c5666de465772c97e29e503fe55f84023c8df1fb`
- GitHub tag and release: `v0.1.0`
- PyPI project: <https://pypi.org/project/aioarubainstant/0.1.0/>
- Release workflow run: `27467750554`

The release workflow built the wheel and source distribution, ran
`twine check`, installed the wheel in a clean environment, and published both
artifacts through PyPI trusted publishing.

## Real-Controller Findings

The local script `scripts/check_real_ap.py` was used against an Aruba Instant
8.6 controller. No real controller output is stored in this repository.

The observations that shaped the implementation were:

- The controller required `--insecure` during local testing because its TLS
  certificate was not trusted by the development environment. Production users
  should supply a trusted CA instead where possible.
- REST communication and authentication succeeded after TLS handling was
  corrected.
- `show client debug` contained the client detail data needed by the models and
  replaced the originally planned combination of `show clients` and debug
  output.
- `show summary` may expose either `Number of Clients : <count>` or a
  standalone `<count> Clients` line.
- Aruba Instant 8.6 may label cluster fields as `Name`, `VC IP Address`, and
  `Master IP Address *`.
- `show aps` exposed the controller-reported client count for each AP.
- Parsed row counts must not be used as authoritative client-count model
  values.

The supported snapshot commands are therefore:

- `show aps`
- `show client debug`
- `show summary`
- `show version`

## Important Decisions

- `show clients` is deliberately unsupported in version 0.1.0.
- Cluster client count comes only from a recognized `show summary` field.
- Per-AP connected-client count comes from `show aps`.
- Client details come from `show client debug`.
- Missing controller fields remain `None`.
- Explicit zero-client debug output becomes an empty client tuple.
- The smoke test remains a one-off local script and is not part of pytest, CI,
  or the release workflow.
- Raw real-controller output may contain IP addresses, MAC addresses, SSIDs,
  hostnames, and other private information and must be reviewed and sanitized
  before it is used as a fixture.
- The repository does not contain Home Assistant imports or entity logic.

## Verification Record

Before release:

- 50 tests passed.
- Total branch-aware coverage was 96.07%, above the required 95%.
- Ruff lint and format checks passed.
- Strict mypy passed.
- `uv lock --check` passed.
- GitHub CI run `27467677415` passed both quality and package jobs.
- A sensitive-data scan found only synthetic documentation/test values,
  including RFC 5737 `192.0.2.0/24` addresses and placeholder credentials.

## Continuing Work

For changes after 0.1.0:

1. Start from `AGENTS.md` and the public contract in `docs/USAGE.md`.
2. Verify assumptions against the official guides or sanitized real-controller
   output.
3. Add focused parser and transport tests before changing behavior.
4. Preserve count provenance and avoid deriving reported values from row
   lengths.
5. Update version references and the changelog together for a release.

## Version 0.1.1 HTTP Compatibility

Testing after version 0.1.0 found that some Aruba Instant login responses
contain a line-break control byte in the `Content-Type` header. aiohttp 3.14.1
accepts that response in its normal lax response mode, but
`PYTHONASYNCIODEBUG=1` enables strict parsing and rejects the response before
the JSON body reaches the library.

Version 0.1.1 uses a dedicated response parser
only for library-owned Aruba controller sessions. It does not disable asyncio
debug mode or change global aiohttp behavior. Caller-provided sessions keep
their caller-selected parser behavior.
