# ruff: noqa: INP001, T201
"""Run a credential-safe one-off check against a real Aruba Instant controller."""

from __future__ import annotations

import argparse
import asyncio
import getpass
import ssl
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Final

from aioarubainstant import (
    ArubaInstantClient,
    ArubaInstantError,
    ArubaInstantSnapshot,
)
from aioarubainstant.parsers import (
    parse_aps,
    parse_client_debug,
    parse_snapshot,
    parse_summary,
    parse_version,
)

if TYPE_CHECKING:
    from collections.abc import Callable

MAX_PORT = 65535
RAW_COMMANDS = (
    "show aps",
    "show client debug",
    "show summary",
    "show version",
)
COMMAND_PREFIX: Final = "COMMAND="


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Authenticate to a real Aruba Instant controller and verify that a complete "
            "monitoring snapshot can be collected and parsed."
        )
    )
    parser.add_argument("host", help="controller hostname, IP address, or HTTPS URL")
    parser.add_argument("username", help="controller username")
    parser.add_argument("--port", type=int, default=4343, help="HTTPS port (default: 4343)")
    parser.add_argument(
        "--timeout",
        type=float,
        default=10.0,
        help="request timeout in seconds (default: 10)",
    )
    output_group = parser.add_mutually_exclusive_group()
    output_group.add_argument(
        "--show-summary",
        action="store_true",
        help="print raw 'show summary' output instead of collecting a snapshot",
    )
    output_group.add_argument(
        "--show-command",
        choices=RAW_COMMANDS,
        help="print raw output for one supported monitoring command",
    )
    output_group.add_argument(
        "--validate-command",
        choices=RAW_COMMANDS,
        help="run and structurally validate one supported monitoring command",
    )
    tls_group = parser.add_mutually_exclusive_group()
    tls_group.add_argument(
        "--ca-file",
        type=Path,
        help="PEM file containing the CA that issued the controller certificate",
    )
    tls_group.add_argument(
        "--insecure",
        action="store_true",
        help="disable TLS certificate verification",
    )
    return parser


def _tls_configuration(args: argparse.Namespace) -> bool | ssl.SSLContext:
    if args.insecure:
        return False
    if args.ca_file is not None:
        return ssl.create_default_context(cafile=args.ca_file)
    return True


async def _collect_outputs(args: argparse.Namespace, password: str) -> dict[str, str]:
    async with ArubaInstantClient(
        args.host,
        args.username,
        password,
        port=args.port,
        verify_ssl=_tls_configuration(args),
        timeout=args.timeout,
    ) as client:
        return {command: await client.async_run_command(command) for command in RAW_COMMANDS}


async def _collect_command(args: argparse.Namespace, password: str, command: str) -> str:
    async with ArubaInstantClient(
        args.host,
        args.username,
        password,
        port=args.port,
        verify_ssl=_tls_configuration(args),
        timeout=args.timeout,
    ) as client:
        return await client.async_run_command(command)


def _print_summary(snapshot: ArubaInstantSnapshot) -> None:
    cluster = snapshot.cluster
    print("Snapshot collected and parsed successfully.")
    print(f"Firmware: {cluster.version or 'unknown'}")
    print(f"Access points: {len(snapshot.access_points)}")
    print(f"Wireless clients: {len(snapshot.clients)}")

    if cluster.ap_count is not None and cluster.ap_count != len(snapshot.access_points):
        print(
            "Warning: controller-reported AP count "
            f"({cluster.ap_count}) differs from parsed count ({len(snapshot.access_points)})."
        )
    if cluster.client_count is not None and cluster.client_count != len(snapshot.clients):
        print(
            "Warning: controller-reported client count "
            f"({cluster.client_count}) differs from parsed count ({len(snapshot.clients)})."
        )


def _validate_envelope(command: str, output: str) -> None:
    if not output.strip():
        msg = "controller returned empty command output"
        raise ValueError(msg)

    command_lines = [
        line.strip()
        for line in output.replace("\r\n", "\n").replace("\r", "\n").splitlines()
        if line.strip().casefold().startswith(COMMAND_PREFIX.casefold())
    ]
    if command_lines and command_lines[0].partition("=")[2].strip() != command:
        msg = f"response identified a different command: {command_lines[0]!r}"
        raise ValueError(msg)


def _validate_aps(output: str) -> str:
    access_points, reported_count = parse_aps(output)
    return f"parsed {len(access_points)} APs; reported count={reported_count}"


def _validate_client_debug(output: str) -> str:
    clients = parse_client_debug(output)
    return f"parsed debug data for {len(clients)} clients"


def _validate_summary(output: str) -> str:
    summary = parse_summary(output)
    populated = sum(
        value is not None
        for value in (
            summary.name,
            summary.management_address,
            summary.master_ap,
            summary.ap_count,
            summary.client_count,
        )
    )
    return f"parsed {populated} recognized summary fields"


def _validate_version(output: str) -> str:
    return f"parsed firmware version {parse_version(output)}"


COMMAND_VALIDATORS: Final[dict[str, Callable[[str], str]]] = {
    "show aps": _validate_aps,
    "show client debug": _validate_client_debug,
    "show summary": _validate_summary,
    "show version": _validate_version,
}


def _validate_output(command: str, output: str) -> str:
    _validate_envelope(command, output)
    return COMMAND_VALIDATORS[command](output)


def _validate_outputs(outputs: dict[str, str]) -> ArubaInstantSnapshot:
    failures: list[str] = []
    for command in RAW_COMMANDS:
        try:
            detail = _validate_output(command, outputs[command])
        except (ArubaInstantError, ValueError) as err:
            failures.append(f"{command}: {type(err).__name__}: {err}")
            print(f"FAIL  {command}: {err}", file=sys.stderr)
        else:
            print(f"PASS  {command}: {detail}")

    if failures:
        msg = f"{len(failures)} command validation(s) failed"
        raise ValueError(msg)

    snapshot = parse_snapshot(outputs)
    print("PASS  combined snapshot: all command outputs are mutually usable")
    return snapshot


def _validate_arguments(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    if args.port < 1 or args.port > MAX_PORT:
        parser.error(f"--port must be between 1 and {MAX_PORT}")
    if args.timeout <= 0:
        parser.error("--timeout must be greater than zero")


def _snapshot_failures(snapshot: ArubaInstantSnapshot) -> list[str]:
    failures: list[str] = []
    if snapshot.cluster.version is None:
        failures.append("controller firmware version was not parsed")
    if not snapshot.access_points:
        failures.append("no access points were parsed")
    return failures


def _run_selected_operation(args: argparse.Namespace, password: str) -> ArubaInstantSnapshot | None:
    command = "show summary" if args.show_summary else args.show_command
    if command is not None:
        print(asyncio.run(_collect_command(args, password, command)))
        return None

    if args.validate_command is not None:
        output = asyncio.run(_collect_command(args, password, args.validate_command))
        print(f"--- raw {args.validate_command} output ---")
        print(output)
        print("--- validation result ---")
        detail = _validate_output(args.validate_command, output)
        print(f"PASS  {args.validate_command}: {detail}")
        return None

    outputs = asyncio.run(_collect_outputs(args, password))
    return _validate_outputs(outputs)


def main(argv: list[str] | None = None) -> int:
    """Run the smoke test and return a process exit status."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    _validate_arguments(args, parser)

    password = getpass.getpass("Controller password: ")
    if not password:
        parser.error("controller password must not be empty")

    if args.insecure:
        print("Warning: TLS certificate verification is disabled.", file=sys.stderr)

    try:
        snapshot = _run_selected_operation(args, password)
    except KeyboardInterrupt:
        print("\nSmoke test cancelled.", file=sys.stderr)
        return 130
    except ArubaInstantError as err:
        print(f"Smoke test failed: {type(err).__name__}: {err}", file=sys.stderr)
        return 1
    except ValueError as err:
        print(f"Validation failed: {err}", file=sys.stderr)
        return 1

    if snapshot is None:
        return 0

    failures = _snapshot_failures(snapshot)
    if failures:
        for failure in failures:
            print(f"Smoke test failed: {failure}.", file=sys.stderr)
        return 1

    _print_summary(snapshot)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
