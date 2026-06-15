"""Parsers for Aruba Instant CLI output returned by the REST API."""

from __future__ import annotations

import re
from dataclasses import replace
from typing import Final

from .exceptions import ArubaInstantParseError
from .models import ArubaAccessPoint, ArubaClient, ArubaCluster, ArubaInstantSnapshot

_DASH_RUN: Final = re.compile(r"-{2,}")
_DIVIDER_LINE: Final = re.compile(r"^[\s-]+$")
_MIN_TABLE_COLUMNS: Final = 2
_MIN_WRAPPED_AP_HEADER_LINES: Final = 2
_MIN_WRAPPED_AP_FIELDS: Final = 6
_INTEGER: Final = re.compile(r"-?\d+")
_MAC_HEX: Final = re.compile(r"^[0-9a-fA-F]{12}$")
_COUNT_APS: Final = re.compile(
    r"^[ \t]*(\d+)[ \t]+Access[ \t]+Points?[ \t]*$",
    re.IGNORECASE | re.MULTILINE,
)
_COUNT_CLIENTS: Final = re.compile(
    r"^[ \t]*(\d+)[ \t]+(?:Wireless[ \t]+)?Clients?[ \t]*$|"
    r"^[ \t]*Number[ \t]+of[ \t]+Clients?[ \t]*:[ \t]*(\d+)[ \t]*$",
    re.IGNORECASE | re.MULTILINE,
)
_SECRET: Final = re.compile(
    r"(?i)(\b(?:sid|passwd|password)\b\s*(?:=|:)\s*)([^\s,}\]]+|\"[^\"]*\")"
)

_AP_NAME = ("name", "ap name", "access point")
_AP_IP = ("ip address", "ap ip address", "ap ip", "ip")
_AP_MAC = ("mac address", "ap mac address", "ap mac", "mac")
_AP_MODEL = ("model", "ap type", "type")
_AP_SERIAL = ("serial #", "serial number", "serial")
_AP_FIRMWARE = ("firmware", "software version", "version")
_AP_CLIENTS = ("connected clients", "client count", "clients")
_AP_MASTER = ("is master", "master")

_CLIENT_MAC = ("mac address", "client mac address", "client mac", "mac", "sta")
_CLIENT_HOSTNAME = ("hostname", "client name", "name")
_CLIENT_IP = ("ip address", "client ip address", "client ip", "ip")
_CLIENT_SSID = ("ssid", "essid", "network")
_CLIENT_BSSID = ("bssid",)
_CLIENT_AP = ("associated ap", "ap name", "access point", "ap")
_CLIENT_SIGNAL = ("signal strength", "signal (dbm)", "signal", "rssi")
_CLIENT_SPEED = ("link speed (mbps)", "link speed", "speed (mbps)", "speed")
_CLIENT_CHANNEL = ("channel",)
_CLIENT_PHY = ("phy mode", "phy", "mode", "type")
_CLIENT_ROLE = ("role",)

_SUMMARY_NAME = ("cluster name", "swarm name", "virtual controller name", "name")
_SUMMARY_ADDRESS = (
    "management address",
    "management ip",
    "virtual controller ip",
    "virtual controller ip address",
    "vc ip address",
)
_SUMMARY_MASTER = (
    "master ap ip address",
    "master ip address",
    "master ip address *",
    "master ap",
    "master ip",
    "master",
)
_SUMMARY_AP_COUNT = ("number of aps", "ap count", "access points", "aps")
_SUMMARY_CLIENT_COUNT = ("number of clients", "client count", "wireless clients", "clients")


def parse_aps(output: str) -> tuple[tuple[ArubaAccessPoint, ...], int | None]:
    """Parse ``show aps`` output."""
    clean = _clean_output(output)
    reported_count = _extract_count(clean, _COUNT_APS)
    if reported_count == 0:
        return (), 0

    try:
        rows = _parse_table(clean, required_headers=(_AP_NAME,))
    except ArubaInstantParseError:
        rows = _parse_wrapped_aps_table(clean)
    access_points: list[ArubaAccessPoint] = []
    for row in rows:
        name = _optional(_lookup(row, _AP_NAME))
        ip_address = _optional(_lookup(row, _AP_IP))
        mac = _normalize_mac(_optional(_lookup(row, _AP_MAC)))
        if name is None and ip_address is None and mac is None:
            continue

        is_master = _parse_master(_lookup(row, _AP_MASTER))
        mode = _optional(row.get("mode"))
        if is_master is None and mode is not None:
            is_master = _parse_master(mode)
        if name is not None and name.endswith("*"):
            name = name.removesuffix("*").rstrip()
            is_master = True

        access_points.append(
            ArubaAccessPoint(
                mac=mac,
                name=name,
                ip_address=ip_address,
                model=_optional(_lookup(row, _AP_MODEL)),
                serial=_optional(_lookup(row, _AP_SERIAL)),
                firmware=_optional(_lookup(row, _AP_FIRMWARE)),
                connected_clients=_parse_int(_lookup(row, _AP_CLIENTS)),
                is_master=is_master,
            )
        )

    if not access_points:
        msg = "show aps did not contain a usable access-point table"
        raise ArubaInstantParseError(msg)
    _validate_reported_count("access points", reported_count, len(access_points))
    return tuple(access_points), reported_count


def _parse_wrapped_aps_table(output: str) -> list[dict[str, str]]:
    """Parse the wrapped multi-line AP table emitted by Aruba Instant 8.6."""
    lines = output.splitlines()
    header_index = next(
        (
            index
            for index, line in enumerate(lines)
            if _canonical(line).startswith("name ip address mode spectrum clients type")
        ),
        None,
    )
    if header_index is None:
        msg = "Command output did not contain the required table headers"
        raise ArubaInstantParseError(msg)

    divider_index = next(
        (index for index in range(header_index + 1, len(lines)) if _is_divider_line(lines[index])),
        None,
    )
    if divider_index is None:
        msg = "Wrapped AP table did not contain a header divider"
        raise ArubaInstantParseError(msg)

    header_lines = divider_index - header_index
    data_index = divider_index
    while data_index < len(lines) and _is_divider_line(lines[data_index]):
        data_index += 1
    data_lines = [line.strip() for line in lines[data_index:] if line.strip()]
    if (
        header_lines < _MIN_WRAPPED_AP_HEADER_LINES
        or not data_lines
        or len(data_lines) % header_lines
    ):
        msg = "Wrapped AP table contained incomplete logical rows"
        raise ArubaInstantParseError(msg)

    rows: list[dict[str, str]] = []
    for offset in range(0, len(data_lines), header_lines):
        primary = data_lines[offset].split()
        continuation = data_lines[offset + 1].split()
        if len(primary) < _MIN_WRAPPED_AP_FIELDS or not continuation:
            msg = "Wrapped AP table contained a malformed access-point row"
            raise ArubaInstantParseError(msg)
        rows.append(
            {
                "name": primary[0],
                "ip address": primary[1],
                "mode": primary[2],
                "clients": primary[4],
                "type": primary[5],
                "serial #": continuation[0],
            }
        )
    return rows


def parse_client_debug(output: str) -> tuple[ArubaClient, ...]:
    """Parse ``show client debug`` table or record output."""
    clean = _clean_output(output)
    if _extract_count(clean, _COUNT_CLIENTS) == 0:
        return ()

    try:
        rows = _parse_table(clean, required_headers=(_CLIENT_MAC,))
    except ArubaInstantParseError:
        rows = _parse_records(clean)

    clients = tuple(_client_from_row(row) for row in rows if _lookup(row, _CLIENT_MAC))
    if not clients:
        msg = "show client debug did not contain usable client records"
        raise ArubaInstantParseError(msg)
    return clients


def parse_summary(output: str) -> ArubaCluster:
    """Parse ``show summary`` output."""
    clean = _clean_output(output)
    values = _parse_key_values(clean)
    ap_count = _parse_int(_lookup(values, _SUMMARY_AP_COUNT))
    client_count = _parse_int(_lookup(values, _SUMMARY_CLIENT_COUNT))
    ap_count = ap_count if ap_count is not None else _extract_count(clean, _COUNT_APS)
    client_count = (
        client_count if client_count is not None else _extract_count(clean, _COUNT_CLIENTS)
    )
    cluster = ArubaCluster(
        name=_optional(_lookup(values, _SUMMARY_NAME)),
        management_address=_optional(_lookup(values, _SUMMARY_ADDRESS)),
        master_ap=_optional(_lookup(values, _SUMMARY_MASTER)),
        ap_count=ap_count,
        client_count=client_count,
    )
    if all(
        value is None
        for value in (
            cluster.name,
            cluster.management_address,
            cluster.master_ap,
            cluster.ap_count,
            cluster.client_count,
        )
    ):
        msg = "show summary did not contain recognized cluster fields"
        raise ArubaInstantParseError(msg)
    return cluster


def parse_version(output: str) -> str:
    """Parse ``show version`` output."""
    clean = _clean_output(output)
    values = _parse_key_values(clean)
    version = _optional(values.get("version"))
    if version is not None:
        return version

    match = re.search(r"\bVersion\s+([A-Za-z0-9][A-Za-z0-9._()/-]*)", clean, re.IGNORECASE)
    if match is None:
        msg = "show version did not contain a software version"
        raise ArubaInstantParseError(msg)
    return match.group(1)


def parse_snapshot(outputs: dict[str, str]) -> ArubaInstantSnapshot:
    """Build a normalized snapshot from all supported command outputs."""
    missing = {
        "show aps",
        "show client debug",
        "show summary",
        "show version",
    } - outputs.keys()
    if missing:
        msg = f"Snapshot is missing command output: {', '.join(sorted(missing))}"
        raise ArubaInstantParseError(msg)

    access_points, ap_count = parse_aps(outputs["show aps"])
    clients = parse_client_debug(outputs["show client debug"])
    summary = parse_summary(outputs["show summary"])
    version = parse_version(outputs["show version"])

    access_points, master_ap = _resolve_master(access_points, summary.master_ap)
    clients = _resolve_associations(clients, access_points)
    cluster = replace(
        summary,
        version=version,
        master_ap=master_ap,
        ap_count=summary.ap_count if summary.ap_count is not None else ap_count,
        client_count=summary.client_count,
    )
    return ArubaInstantSnapshot(
        cluster=cluster,
        access_points=access_points,
        clients=clients,
        _raw_output={command: sanitize_output(output) for command, output in outputs.items()},
    )


def sanitize_output(output: str) -> str:
    """Normalize line endings and redact accidental session or password values."""
    return _SECRET.sub(r"\1<redacted>", output.replace("\r\n", "\n").replace("\r", "\n"))


def _clean_output(output: str) -> str:
    lines = sanitize_output(output).splitlines()
    cleaned = [
        line.rstrip()
        for line in lines
        if line.strip().casefold() != "cli output:"
        and not line.strip().casefold().startswith("command=")
    ]
    return "\n".join(cleaned).strip()


def _parse_table(
    output: str,
    *,
    required_headers: tuple[tuple[str, ...], ...],
) -> list[dict[str, str]]:
    lines = output.splitlines()
    for divider_index, divider in enumerate(lines):
        spans = list(_DASH_RUN.finditer(divider))
        if not _is_divider_line(divider) or divider_index == 0:
            continue
        header = lines[divider_index - 1]
        starts = [span.start() for span in spans]
        headers = [
            _canonical(header[start : starts[index + 1] if index + 1 < len(starts) else None])
            for index, start in enumerate(starts)
        ]
        if any(not any(alias in headers for alias in aliases) for aliases in required_headers):
            continue

        rows: list[dict[str, str]] = []
        for line in lines[divider_index + 1 :]:
            if not line.strip():
                if rows:
                    break
                continue
            if _is_divider_line(line):
                continue
            values = [
                line[start : starts[index + 1] if index + 1 < len(starts) else None].strip()
                for index, start in enumerate(starts)
            ]
            row = {name: value for name, value in zip(headers, values, strict=True) if name}
            if any(row.values()):
                rows.append(row)
        return rows

    msg = "Command output did not contain the required table headers"
    raise ArubaInstantParseError(msg)


def _parse_records(output: str) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    current: dict[str, str] = {}
    for line in output.splitlines():
        if not line.strip():
            if current:
                records.append(current)
                current = {}
            continue
        match = re.match(r"^\s*([^:=]+?)\s*[:=]\s*(.*?)\s*$", line)
        if match is None:
            continue
        key = _canonical(match.group(1))
        if key in _CLIENT_MAC and _lookup(current, _CLIENT_MAC):
            records.append(current)
            current = {}
        current[key] = match.group(2)
    if current:
        records.append(current)
    return records


def _is_divider_line(line: str) -> bool:
    return bool(
        _DIVIDER_LINE.fullmatch(line) and len(_DASH_RUN.findall(line)) >= _MIN_TABLE_COLUMNS
    )


def _parse_key_values(output: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in output.splitlines():
        match = re.match(r"^\s*([^:=]+?)\s*[:=]\s*(.*?)\s*$", line)
        if match is not None:
            values[_canonical(match.group(1))] = match.group(2).strip()
    return values


def _client_from_row(row: dict[str, str]) -> ArubaClient:
    mac = _normalize_mac(_optional(_lookup(row, _CLIENT_MAC)))
    if mac is None:
        msg = "Client row does not contain a valid MAC address"
        raise ArubaInstantParseError(msg)
    return ArubaClient(
        mac=mac,
        hostname=_optional(_lookup(row, _CLIENT_HOSTNAME)),
        ip_address=_optional(_lookup(row, _CLIENT_IP)),
        ssid=_optional(_lookup(row, _CLIENT_SSID)),
        bssid=_normalize_mac(_optional(_lookup(row, _CLIENT_BSSID))),
        associated_ap=_optional(_lookup(row, _CLIENT_AP)),
        signal_strength=_parse_int(_lookup(row, _CLIENT_SIGNAL)),
        link_speed=_parse_int(_lookup(row, _CLIENT_SPEED)),
        channel=_parse_int(_lookup(row, _CLIENT_CHANNEL)),
        phy_mode=_optional(_lookup(row, _CLIENT_PHY)),
        role=_optional(_lookup(row, _CLIENT_ROLE)),
    )


def _resolve_master(
    access_points: tuple[ArubaAccessPoint, ...], master: str | None
) -> tuple[tuple[ArubaAccessPoint, ...], str | None]:
    if master is None:
        marked = next((ap for ap in access_points if ap.is_master), None)
        return access_points, _ap_identifier(marked) if marked is not None else None

    normalized_master = _identifier(master)
    matched = next(
        (
            ap
            for ap in access_points
            if normalized_master
            in {_identifier(ap.name), _identifier(ap.ip_address), _identifier(ap.mac)}
        ),
        None,
    )
    if matched is None:
        return access_points, master
    return (
        tuple(replace(ap, is_master=ap == matched) for ap in access_points),
        _ap_identifier(matched),
    )


def _resolve_associations(
    clients: tuple[ArubaClient, ...], access_points: tuple[ArubaAccessPoint, ...]
) -> tuple[ArubaClient, ...]:
    identifiers: dict[str, str] = {}
    for access_point in access_points:
        canonical = _ap_identifier(access_point)
        if canonical is None:
            continue
        for value in (access_point.name, access_point.ip_address, access_point.mac):
            if value is not None:
                identifiers[_identifier(value)] = canonical
    return tuple(
        replace(
            client,
            associated_ap=identifiers.get(_identifier(client.associated_ap), client.associated_ap),
        )
        for client in clients
    )


def _ap_identifier(access_point: ArubaAccessPoint | None) -> str | None:
    if access_point is None:
        return None
    return access_point.name or access_point.mac or access_point.ip_address


def _identifier(value: str | None) -> str:
    return value.strip().casefold() if value is not None else ""


def _lookup(row: dict[str, str], aliases: tuple[str, ...]) -> str | None:
    return next((row[alias] for alias in aliases if alias in row), None)


def _canonical(value: str) -> str:
    return " ".join(value.strip().casefold().replace("_", " ").split())


def _optional(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return None if stripped in {"", "-", "--", "N/A", "n/a"} else stripped


def _normalize_mac(value: str | None) -> str | None:
    if value is None:
        return None
    compact = re.sub(r"[.:-]", "", value)
    if _MAC_HEX.fullmatch(compact):
        return ":".join(compact[index : index + 2] for index in range(0, 12, 2)).lower()
    return None


def _parse_int(value: str | None) -> int | None:
    optional = _optional(value)
    if optional is None:
        return None
    match = _INTEGER.search(optional)
    return int(match.group()) if match is not None else None


def _parse_master(value: str | None) -> bool | None:
    optional = _optional(value)
    if optional is None:
        return None
    normalized = optional.casefold()
    if normalized in {"yes", "true", "master", "*"}:
        return True
    if normalized in {"no", "false", "slave"}:
        return False
    return None


def _extract_count(output: str, pattern: re.Pattern[str]) -> int | None:
    match = pattern.search(output)
    if match is None:
        return None
    value = next((group for group in match.groups() if group is not None), None)
    return int(value) if value is not None else None


def _validate_reported_count(label: str, reported: int | None, parsed: int) -> None:
    if reported is not None and reported != parsed:
        msg = f"Controller reported {reported} {label}, but {parsed} rows were parsed"
        raise ArubaInstantParseError(msg)
