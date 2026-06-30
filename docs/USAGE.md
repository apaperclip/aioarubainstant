# Package Usage

This guide summarizes the public contract of `aioarubainstant 0.1.4` for
application and Home Assistant integration authors.

## Installation

```bash
python -m pip install aioarubainstant==0.1.4
```

Home Assistant manifest requirement:

```json
"requirements": ["aioarubainstant==0.1.4"]
```

The package requires Python 3.14 or newer and has no Home Assistant dependency.
Version 0.1.4 allows Home Assistant environments pinned to `aiohttp==3.13.5`.

## Collecting a Snapshot

```python
from aioarubainstant import ArubaInstantClient


async def collect() -> None:
    async with ArubaInstantClient(
        "controller.example.com",
        "admin",
        "password",
        verify_ssl=True,
    ) as client:
        snapshot = await client.async_get_snapshot()

    print(snapshot.cluster)
    print(snapshot.access_points)
    print(snapshot.clients)
```

The default HTTPS port is `4343`. `verify_ssl` accepts `True`, `False`, or an
`ssl.SSLContext`. Prefer an SSL context that trusts the controller's private CA
instead of disabling verification.

`async_get_snapshot()` is also available as a convenience function:

```python
from aioarubainstant import async_get_snapshot

snapshot = await async_get_snapshot(
    "controller.example.com",
    "admin",
    "password",
)
```

The convenience function creates and closes a short-lived client. When using
`ArubaInstantClient` directly, close its context or call `async_close()` to log
out. A caller-provided `aiohttp.ClientSession` remains owned by the caller and
is not closed by the library.

For Aruba firmware that emits malformed HTTP response headers, let
`ArubaInstantClient` create its own session. The internally owned session uses
controller-scoped compatibility parsing even when `PYTHONASYNCIODEBUG=1` makes
aiohttp strict. A caller-provided session keeps its own connector and parser
behavior. This compatibility behavior is included in version 0.1.1 and later.

## Snapshot Contract

All models are frozen dataclasses. Collections are tuples, so one snapshot is a
stable point-in-time value.

`ArubaCluster` fields:

- `name`
- `management_address`
- `version`
- `master_ap`
- `ap_count`
- `client_count`

`ArubaAccessPoint` fields:

- `mac`
- `name`
- `ip_address`
- `model`
- `serial`
- `firmware`
- `connected_clients`
- `is_master`

`ArubaClient` fields:

- `mac`
- `hostname`
- `ip_address`
- `ssid`
- `bssid`
- `associated_ap`
- `signal_strength`
- `link_speed`
- `channel`
- `phy_mode`
- `role`

Except for `ArubaClient.mac`, fields may be `None` when the controller does not
report them. The library does not invent placeholder values.

Cluster and per-AP client counts are values reported by the controller. They
are not derived from `len(snapshot.clients)`, so a temporary mismatch can occur
when command outputs represent slightly different controller instants.

## Exceptions

Catch `ArubaInstantError` for all package errors, or use a specific subclass:

- `ArubaInstantAuthenticationError`
- `ArubaInstantConnectionError`
- `ArubaInstantTimeoutError`
- `ArubaInstantRestDisabledError`
- `ArubaInstantNotMasterError`
- `ArubaInstantSessionError`
- `ArubaInstantCommandError`
- `ArubaInstantParseError`

`ArubaInstantTimeoutError` is also an
`ArubaInstantConnectionError`. `ArubaInstantSessionError` is also an
`ArubaInstantAuthenticationError`.

The client automatically retries once after an expired or invalid SID. An
exception after that retry should be surfaced to the integration rather than
retried in a tight loop.

## Update Coordination

An integration should normally keep one `ArubaInstantClient`, serialize refresh
cycles at its own coordinator boundary, and call `async_get_snapshot()` once
per refresh. The client itself serializes controller commands.

Use the model values directly:

- Use `snapshot.cluster.client_count` for the controller-reported cluster count.
- Use `access_point.connected_clients` for controller-reported per-AP counts.
- Use `snapshot.clients` for individual client records.
- Use client MAC addresses as stable identities when present in controller
  output.

Do not access `snapshot._raw_output`; it is private diagnostic state and is not
part of the public compatibility contract.
