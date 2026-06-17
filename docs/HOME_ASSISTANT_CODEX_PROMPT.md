# Codex Goal Prompt: Modernize Home Assistant Aruba

Copy the prompt below into Codex while working in a checkout of
`home-assistant/core`. If the `aioarubainstant` repository is available locally,
replace `<AIOARUBAINSTANT_REPO>` with its absolute path. Otherwise Codex should
use the linked files on GitHub.

---

Create an explicit goal and pursue it autonomously until all achievable work is
complete:

Modernize the existing Home Assistant `aruba` integration to use
`aioarubainstant`, replacing its legacy synchronous SSH/`pexpect`
implementation with a modern asynchronous Aruba Instant REST integration while
preserving reliable client presence tracking. Determine the architecture,
components, lifecycle, and user experience from the current Home Assistant
developer documentation before implementing them.

## Repositories and references

Primary workspace:

- Home Assistant Core: <https://github.com/home-assistant/core>
- Existing integration:
  `homeassistant/components/aruba`
- Existing integration source:
  <https://github.com/home-assistant/core/tree/dev/homeassistant/components/aruba>
- Current user documentation:
  <https://www.home-assistant.io/integrations/aruba/>
- Documentation source:
  <https://github.com/home-assistant/home-assistant.io/blob/current/source/_integrations/aruba.markdown>

Home Assistant architecture authority:

- Developer documentation: <https://developers.home-assistant.io/>
- Building integrations:
  <https://developers.home-assistant.io/docs/creating_component_index/>
- Integration file structure:
  <https://developers.home-assistant.io/docs/creating_integration_file_structure/>
- Integration test structure:
  <https://developers.home-assistant.io/docs/creating_integration_tests_file_structure/>
- Integration manifest:
  <https://developers.home-assistant.io/docs/creating_integration_manifest/>
- Config entries:
  <https://developers.home-assistant.io/docs/config_entries_index/>
- Config flow:
  <https://developers.home-assistant.io/docs/core/integration/config_flow/>
- Fetching data:
  <https://developers.home-assistant.io/docs/integration_fetching_data/>
- Setup failures:
  <https://developers.home-assistant.io/docs/integration_setup_failures/>
- Entities:
  <https://developers.home-assistant.io/docs/core/entity/>
- Devices and services:
  <https://developers.home-assistant.io/docs/device_registry_index/>
- Integration Quality Scale:
  <https://developers.home-assistant.io/docs/core/integration-quality-scale/>
- Development checklist:
  <https://developers.home-assistant.io/docs/development_checklist/>

Required library documentation, in reading order:

1. `<AIOARUBAINSTANT_REPO>/AGENTS.md`
2. `<AIOARUBAINSTANT_REPO>/docs/USAGE.md`
3. `<AIOARUBAINSTANT_REPO>/docs/PROJECT_NOTES.md`
4. `<AIOARUBAINSTANT_REPO>/README.md`

If that repository is not local, use:

1. <https://github.com/apaperclip/aioarubainstant/blob/main/AGENTS.md>
2. <https://github.com/apaperclip/aioarubainstant/blob/main/docs/USAGE.md>
3. <https://github.com/apaperclip/aioarubainstant/blob/main/docs/PROJECT_NOTES.md>
4. <https://github.com/apaperclip/aioarubainstant/blob/main/README.md>

Also inspect repository-local instructions, current device tracker conventions,
testing guidance, dependency tooling, and at least one comparable modern
local-network integration before editing. Treat the current `dev` branch and
current developer documentation as time-sensitive and re-read them rather than
relying on remembered Home Assistant patterns.

## Authority and conflict resolution

Use this hierarchy throughout the work:

1. The current Home Assistant developer documentation is authoritative for the
   integration architecture, files, config-entry lifecycle, setup and unload,
   config and options flows, reauthentication, reconfiguration, polling,
   coordinator use, entities, devices, diagnostics, translations, testing,
   quality rules, and contribution requirements.
2. Repository-local instructions and accepted code on the current Home
   Assistant `dev` branch are authoritative for implementation details and
   tooling not fully specified by the developer documentation.
3. The `aioarubainstant` Markdown files listed below and its installed public
   API are authoritative for library usage, exception behavior, models,
   command selection, field meaning, and count provenance.
4. The existing Aruba integration and user documentation describe behavior and
   migration context only. They are not architectural templates.
5. Comparable integrations are examples, not authority. Do not copy legacy or
   integration-specific patterns when current developer documentation says
   otherwise.

If this prompt suggests an implementation detail that conflicts with current
Home Assistant developer documentation, follow the developer documentation and
record the reason in the final summary. Do not override the non-negotiable
library semantics or security requirements below.

## Known starting state

At the time this prompt was written, the Aruba integration was a legacy YAML
`device_tracker` with only `__init__.py`, `device_tracker.py`, and
`manifest.json`. It used synchronous `pexpect`, launched `ssh`, ran
`show clients`, had no config flow, and had no integration tests. Its public
documentation incorrectly said telnet was required.

Home Assistant `dev` required Python 3.14.2 or newer, making
`aioarubainstant==0.1.3` compatible. Re-verify all of these facts before
implementation rather than assuming they remain current.

## Non-negotiable library behavior

Use the public `aioarubainstant` API; do not copy its transport or parsers into
Home Assistant.

The library snapshot uses exactly:

- `show aps`
- `show client debug`
- `show summary`
- `show version`

Do not restore or separately issue `show clients`. Do not issue per-client
`show client status <mac>` calls.

Count provenance is authoritative:

- Cluster client count comes from `show summary`.
- Per-AP client count comes from `show aps`.
- Client records come from `show client debug`.
- Never replace reported counts with `len(snapshot.clients)`.

Do not access the private `snapshot._raw_output` attribute from Home Assistant.
Do not log credentials, session IDs, or raw controller output.

## Required outcome

Produce a focused, review-ready Home Assistant Core migration with these
minimum behaviors:

1. Replace `pexpect` and SSH command parsing with
   `aioarubainstant==0.1.3` in `manifest.json`.
2. Use asynchronous Home Assistant APIs only. Do not call blocking network or
   subprocess APIs in the event loop.
3. Add a UI config flow that validates a real snapshot before creating an
   entry.
4. Support host, username, password, HTTPS port with default `4343`, and TLS
   verification using current Home Assistant constants, selectors, and UX
   conventions. Default to secure certificate verification unless current
   Home Assistant policy or an explicit product decision says otherwise.
5. Explain in the UI and documentation that the REST API must be enabled on the
   Aruba Instant master AP with `allow-rest-api`.
6. Prevent duplicate entries using the most stable cluster identity available
   from the snapshot. Prefer the normalized virtual-controller management
   address when present, with a carefully tested normalized-host fallback.
   Do not use the current master AP MAC as the cluster identity because
   mastership can move between APs.
7. Implement reauthentication for invalid credentials and reconfiguration for
   connection settings according to current Home Assistant developer
   documentation.
8. Store typed runtime state using the current documented config-entry pattern.
9. Reuse one client according to the current external-API and config-entry
   lifecycle guidance. Verify the pinned `aioarubainstant` release's malformed
   Aruba HTTP-header compatibility behavior before deciding session ownership.
   Releases containing that compatibility fix require the library-owned session
   path; a caller-provided Home Assistant session retains aiohttp's strict
   parser under `PYTHONASYNCIODEBUG=1`. Avoid a new login and HTTP session for
   every entity or every command.
10. Use the data-fetching architecture prescribed by current Home Assistant
    developer documentation to fetch exactly one complete snapshot per refresh.
    If that guidance calls for a `DataUpdateCoordinator`, implement it using
    the current documented APIs. Choose and justify a conservative local
    polling interval; do not hammer the controller with parallel refreshes.
11. Close/logout the library client on config-entry unload and support clean
    reloads.
12. Preserve the existing integration's essential user-facing behavior:
    active Aruba clients appear as device tracker entities with stable MAC
    unique IDs, hostname/name where present, IP address where present, and
    connected state based on presence in the latest snapshot.
13. Dynamically add newly seen clients without reloading the integration.
14. Preserve known tracker entities when clients go offline or Home Assistant
    restarts, so they become disconnected instead of disappearing. Follow a
    current accepted entity-registry restoration pattern.
15. Mark entities unavailable when the coordinator is unavailable and avoid
    falsely turning every client away because one refresh failed.
16. Use cluster/AP metadata for device registry relationships or diagnostics
    only where it is reliable and follows current Home Assistant conventions.
    Do not invent identifiers or values absent from the library models.
    `snapshot.cluster.master_ap` and each AP's `is_master` field indicate the
    currently active/master AP when the controller output permits resolution.
    Use those values only where the Home Assistant architecture and entity
    model call for them; do not use the current master AP as the config-entry
    unique ID because mastership can move.
17. Do not add sensor entities merely because the library exposes AP and
    cluster counts. Keep this migration focused on presence parity unless a
    linked issue, maintainer requirement, or explicit user instruction requires
    sensors. Record sensible follow-up work separately.
18. Add translations/strings and manifest metadata required by current Home
    Assistant validation. Determine `integration_type`, quality metadata, and
    all manifest fields from the current developer documentation. The
    integration communicates locally by polling, so retain `local_polling`
    unless authoritative Home Assistant guidance defines a more accurate
    classification.
19. Remove obsolete `pexpect` loggers and dependency references. Regenerate
    Home Assistant dependency files using repository tooling; do not hand-edit
    generated files unless repository instructions require it.
20. Support unloading and setup retry behavior correctly.

## Exception mapping

Inspect the package exception hierarchy and implement deliberate mappings:

- Authentication/session failures that remain after the library's one retry:
  trigger `ConfigEntryAuthFailed` and reauthentication.
- Connection and timeout failures: setup retry or coordinator `UpdateFailed`,
  depending on lifecycle stage.
- REST-disabled and non-master errors: give the user actionable, translated
  setup/config-flow feedback and do not leak controller details.
- Command and parse failures: fail the update without replacing the previous
  good coordinator data.
- Unexpected exceptions: log once with useful context but no secrets, and use
  the current Home Assistant error-handling convention.

Do not wrap every package exception into a generic error if Home Assistant can
provide a more useful lifecycle response.

## YAML migration and compatibility

The existing integration is configured under legacy
`device_tracker: - platform: aruba` YAML. Investigate the current Home Assistant
policy and recent accepted migrations from legacy scanner platforms to config
entries before choosing a migration strategy.

Required principles:

- Do not silently maintain two independent polling implementations.
- Do not silently discard existing users' configuration.
- If supported by current architecture, import legacy YAML into a config flow
  or config entry and clearly deprecate the old path.
- If automatic import is impossible or no longer accepted, implement the
  repository-approved transition and document the exact breaking-change and
  manual migration steps.
- Test whichever migration path is selected.

The old integration used SSH and the new integration uses the REST API, so
existing credentials alone do not guarantee migration success. REST may need
to be enabled and TLS trust configured. Surface this honestly rather than
pretending the transport change is transparent.

## Testing requirements

Create `tests/components/aruba/` and achieve strong coverage of every new
integration module. Use package objects or realistic immutable models, but mock
network I/O and the library client boundary. Never connect to a real AP in
Home Assistant tests.

At minimum test:

- Successful user config flow and connection validation
- Duplicate prevention and stable unique ID selection
- Invalid authentication
- Connection timeout/failure
- REST API disabled
- Request sent to a non-master AP
- Malformed/unsupported command output
- Reauthentication success and failure
- Reconfigure success, duplicate protection, and failure
- Initial setup, first refresh, retry behavior, unload, and client cleanup
- Coordinator exception mapping and retention of last good data
- Device tracker creation, MAC normalization, hostname, and IP address
- Dynamic discovery of clients after setup
- Client roaming without entity identity churn
- Client disappearance becoming disconnected
- Entity restoration after restart while a client is offline
- Explicit zero-client snapshots
- Reported client counts differing from parsed client records without changing
  tracker identity or deriving counts
- TLS verification and custom/default port data reaching the library client
- YAML import or the selected legacy transition path
- Diagnostics, if implemented, with credentials and private raw output absent
- No secret values in logs

Use Home Assistant fixtures and conventions already present on `dev`. Avoid
over-mocking internal Home Assistant implementation details.

## Documentation work

Prepare the corresponding change for the
`home-assistant/home-assistant.io` repository. Core and documentation changes
may need separate commits or pull requests.

Update the Aruba page to:

- Remove the incorrect telnet statement and obsolete SSH/YAML instructions.
- Explain UI setup step by step.
- Document the Aruba Instant REST prerequisite and master-AP requirement.
- Document HTTPS port `4343` and TLS verification behavior.
- Describe the device tracker entities and polling behavior.
- Explain migration for existing YAML/SSH users.
- Describe known limitations, including active-client-only presence and the
  possibility that controller commands represent slightly different instants.
- Preserve only genuinely verified device compatibility claims.
- Include troubleshooting for authentication, REST disabled, non-master AP,
  certificate verification, timeout, and malformed controller output.
- Follow the current Home Assistant documentation template and quality rules.

## Scope control

- Keep changes confined to the Aruba integration, its tests, generated
  dependency files, and its documentation unless a shared change is genuinely
  required.
- Do not modify `aioarubainstant` merely to avoid understanding its public API.
- If a real library defect blocks the integration, reproduce it in the library
  repository, add a focused regression test, fix it there, release a new
  package version, and then update Home Assistant's pinned requirement. Never
  point Home Assistant at an unreleased Git commit or vendor a private patch.
- Do not add speculative abstractions, services, switches, sensors, or options.
- Do not commit credentials, controller output, IP addresses, MAC addresses,
  SSIDs, hostnames, or other private data. Use Home Assistant test constants and
  documentation ranges.
- Do not claim an Integration Quality Scale tier unless every required rule for
  that tier is demonstrably satisfied. Add or update quality metadata honestly.

## Autonomous goal loop

Follow this loop until the terminal conditions are met:

1. Inspect the workspace, repository instructions, current Aruba code, tests,
   manifest, generated requirements, and relevant current integrations.
2. Read the relevant current Home Assistant developer-documentation pages and
   write a short architecture decision summary before editing. Cite which
   documented patterns determine setup, runtime data, polling, entities,
   migration, tests, and unload behavior.
3. Verify current upstream facts: Home Assistant Python support,
   `aioarubainstant` release availability, package API, and contribution rules.
4. Create and maintain a concrete task plan. Keep exactly one implementation
   step in progress at a time.
5. Implement one coherent section, starting with architecture/runtime setup,
   then config flow, the documented data-fetching layer, entities, migration,
   tests, and docs.
6. Run the narrowest relevant tests and validation after each section.
7. Diagnose failures and continue; do not stop after proposing a fix.
8. Re-read the diff for regressions, blocking I/O, secret exposure, stale
   legacy behavior, generated-file drift, and unnecessary scope.
9. Run the complete targeted integration test suite and all repository-required
   lint, typing, manifest, translation, dependency, and formatting checks.
10. Review the result against every required outcome and test above. Add missing
   coverage or implementation before declaring completion.
11. Commit the coherent changes. Push and open draft pull requests only if the
    user has authorized GitHub publication and authentication is available.

Ask the user only when genuinely blocked by credentials, permissions, a
required real-controller observation, an unavailable repository, or a product
decision that cannot safely be inferred. Do not ask for routine implementation
choices that can be resolved from Home Assistant conventions and the package
documentation.

## Verification commands

Discover and follow the current commands documented by Home Assistant rather
than relying blindly on this list. At minimum run the equivalent of:

```bash
pytest -q tests/components/aruba
pre-commit run --files homeassistant/components/aruba/* tests/components/aruba/*
python -m script.hassfest
```

Run requirement-generation and translation validation tools when their inputs
change. Run broader tests when shared or generated files are affected. If a
command cannot run because the development environment is incomplete, explain
the exact limitation and still run every available targeted check.

## Terminal conditions

Do not mark the goal complete until:

- The integration no longer uses `pexpect`, SSH, or local CLI parsing.
- UI setup, validation, reauth, reconfigure, unload, and polling work.
- Presence behavior is preserved with stable device tracker identities.
- Legacy YAML users have a tested, documented transition.
- Required tests and Home Assistant validation pass.
- The manifest pins a released, compatible `aioarubainstant` version.
- Documentation changes are prepared and accurate.
- No credentials, raw controller data, or PII are present in the diff.
- The final response lists changed files, tests run, residual risks, and any
  external actions still required.

---
