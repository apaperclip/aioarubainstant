# Changelog

All notable changes to this project are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.1] - 2026-06-14

### Fixed

- Accept malformed Aruba Instant response headers when aiohttp strict response
  parsing is enabled by `PYTHONASYNCIODEBUG`, without disabling asyncio debug
  mode globally.

## [0.1.0] - 2026-06-13

### Added

- Asynchronous HTTPS transport for the Aruba Instant REST API.
- SID authentication, reuse, logout, and one-time expired-session recovery.
- Monitoring support for APs, detailed client data, cluster summary, and
  software version using `show aps`, `show client debug`, `show summary`, and
  `show version`.
- Immutable typed cluster, AP, client, and snapshot models.
- Header-derived parsers with malformed-output and zero-client protection.
- Strict linting, typing, tests, coverage, package validation, and release CI.

[0.1.0]: https://github.com/apaperclip/aioarubainstant/releases/tag/v0.1.0
[0.1.1]: https://github.com/apaperclip/aioarubainstant/releases/tag/v0.1.1
