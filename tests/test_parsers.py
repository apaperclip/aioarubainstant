from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from aioarubainstant import ArubaAccessPoint, ArubaInstantParseError
from aioarubainstant.parsers import (
    parse_aps,
    parse_client_debug,
    parse_clients,
    parse_snapshot,
    parse_summary,
    parse_version,
    sanitize_output,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

FIXTURES = Path(__file__).parent / "fixtures"


def render_table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    widths = [
        max([len(header), *(len(row[index]) for row in rows)]) + 2
        for index, header in enumerate(headers)
    ]

    def render(values: Sequence[str]) -> str:
        return "".join(
            value.ljust(width) for value, width in zip(values, widths, strict=True)
        ).rstrip()

    divider = render(["-" * (width - 2) for width in widths])
    return "\n".join([render(headers), divider, *(render(row) for row in rows)])


APS_TABLE = render_table(
    [
        "Name",
        "IP Address",
        "Mode",
        "Clients",
        "Type",
        "Serial #",
        "MAC Address",
        "Firmware",
        "Extra Column",
    ],
    [
        [
            "lobby",
            "192.0.2.10",
            "access",
            "1",
            "AP-515",
            "CN123",
            "aa:bb:cc:00:00:01",
            "8.6.0.22",
            "ignored",
        ],
        [
            "office",
            "192.0.2.11",
            "access",
            "0",
            "AP-505",
            "CN124",
            "aa:bb:cc:00:00:02",
            "8.6.0.22",
            "ignored",
        ],
    ],
)

CLIENTS_TABLE = render_table(
    ["Role", "MAC Address", "IP Address", "Name", "Network", "Access Point", "Extra"],
    [
        [
            "employee",
            "11-22-33-44-55-66",
            "192.0.2.100",
            "phone",
            "Staff",
            "192.0.2.10",
            "ignored",
        ]
    ],
)

DEBUG_TABLE = render_table(
    ["MAC", "BSSID", "RSSI", "Speed (Mbps)", "Channel", "PHY Mode", "AP Name"],
    [
        [
            "1122.3344.5566",
            "aa:bb:cc:dd:ee:ff",
            "-55(good)",
            "866",
            "36",
            "802.11ax",
            "lobby",
        ]
    ],
)


def command_output(command: str, body: str, *, crlf: bool = False) -> str:
    output = f"cli output:\nCOMMAND={command}\n\n{body}\n"
    return output.replace("\n", "\r\n") if crlf else output


def snapshot_outputs(*, associated_ap: str = "192.0.2.10") -> dict[str, str]:
    clients = CLIENTS_TABLE.replace("192.0.2.10", associated_ap)
    return {
        "show aps": command_output("show aps", f"2 Access Points\n{APS_TABLE}"),
        "show clients": command_output("show clients", f"1 Client\n{clients}"),
        "show client debug": command_output("show client debug", DEBUG_TABLE),
        "show summary": command_output(
            "show summary",
            "Cluster Name : Office\nVirtual Controller IP : 192.0.2.1\n"
            "Master AP : 192.0.2.10\nAccess Points : 2\nClients : 1",
        ),
        "show version": command_output("show version", "ArubaOS (MODEL: 515), Version 8.6.0.22"),
    }


def test_parse_aps_from_header_spans_with_crlf_and_extra_column() -> None:
    access_points, count = parse_aps(
        command_output("show aps", f"2 Access Points\n{APS_TABLE}", crlf=True)
    )

    assert count == 2
    assert access_points[0].name == "lobby"
    assert access_points[0].mac == "aa:bb:cc:00:00:01"
    assert access_points[0].model == "AP-515"
    assert access_points[0].connected_clients == 1
    assert access_points[1].serial == "CN124"


def test_zero_aps_and_master_marker_variants() -> None:
    assert parse_aps("0 Access Points") == ((), 0)

    marked_table = render_table(
        ["Name", "IP Address", "Mode", "Master"],
        [
            ["lobby*", "192.0.2.10", "access", ""],
            ["office", "192.0.2.11", "slave", "no"],
        ],
    )
    access_points, _ = parse_aps(marked_table)
    assert access_points[0].name == "lobby"
    assert access_points[0].is_master is True
    assert access_points[1].is_master is False


def test_parse_wrapped_aruba_8_6_access_point_table() -> None:
    output = (FIXTURES / "show_aps_8_6_wrapped.txt").read_text()

    access_points, count = parse_aps(output)

    assert count == 1
    assert access_points == (
        ArubaAccessPoint(
            name="lobby",
            ip_address="192.0.2.10",
            model="225(indoor)",
            serial="CN123456",
            connected_clients=2,
        ),
    )


@pytest.mark.parametrize(
    "output",
    [
        "Name IP Address Mode Spectrum Clients Type\nno divider",
        "Name IP Address Mode Spectrum Clients Type\nSerial # radio0 Channel\n"
        "---- ---------- ---- -------- ------- ----\n------- --------------\n"
        "lobby 192.0.2.10 access disable 2\nCN123 36",
        "Name IP Address Mode Spectrum Clients Type\nSerial # radio0 Channel\n"
        "---- ---------- ---- -------- ------- ----\n------- --------------\n"
        "lobby 192.0.2.10 access disable 2 225(indoor)",
    ],
)
def test_malformed_wrapped_access_point_tables_raise(output: str) -> None:
    with pytest.raises(ArubaInstantParseError):
        parse_aps(output)


def test_access_point_table_with_no_usable_rows_is_malformed() -> None:
    empty_row = render_table(["Name", "IP Address"], [["", ""]])
    with pytest.raises(ArubaInstantParseError, match="usable access-point table"):
        parse_aps(empty_row)


def test_parse_clients_reordered_columns_and_blank_values() -> None:
    clients, count = parse_clients(command_output("show clients", f"1 Client\n{CLIENTS_TABLE}"))

    assert count == 1
    assert clients[0].mac == "11:22:33:44:55:66"
    assert clients[0].hostname == "phone"
    assert clients[0].ssid == "Staff"
    assert clients[0].role == "employee"
    assert clients[0].signal_strength is None


def test_alias_precedence_is_deterministic() -> None:
    table = render_table(
        ["MAC", "Name", "Hostname", "Network", "SSID", "Speed", "Link Speed"],
        [["11:22:33:44:55:66", "fallback", "preferred", "old", "new", "54", "866"]],
    )

    client = parse_clients(table)[0][0]

    assert client.hostname == "preferred"
    assert client.ssid == "new"
    assert client.link_speed == 866


def test_parse_client_debug_table_and_records() -> None:
    table_client = parse_client_debug(command_output("show client debug", DEBUG_TABLE))[0]
    assert table_client.mac == "11:22:33:44:55:66"
    assert table_client.signal_strength == -55
    assert table_client.link_speed == 866
    assert table_client.phy_mode == "802.11ax"

    records = """Client MAC: aa:bb:cc:dd:ee:01
Hostname: tablet
SSID: Guest
BSSID: aa:bb:cc:00:00:02
Signal: -61 dBm
Channel: 44

Client MAC: aa:bb:cc:dd:ee:02
Hostname: laptop
"""
    record_clients = parse_client_debug(command_output("show client debug", records))
    assert len(record_clients) == 2
    assert record_clients[0].hostname == "tablet"
    assert record_clients[0].channel == 44

    adjacent_records = "Client MAC: aa:bb:cc:dd:ee:03\nClient MAC: aa:bb:cc:dd:ee:04"
    assert len(parse_client_debug(adjacent_records)) == 2


def test_parse_summary_and_version_variants() -> None:
    summary = parse_summary(
        "Cluster Name = Office\nManagement Address: 192.0.2.1\n"
        "Master AP: lobby\n2 Access Points\n1 Client"
    )
    assert summary.name == "Office"
    assert summary.management_address == "192.0.2.1"
    assert summary.master_ap == "lobby"
    assert summary.ap_count == 2
    assert summary.client_count == 1
    assert parse_version("Version: 8.6.0.22") == "8.6.0.22"
    assert parse_version("ArubaOS, Version 8.10.0.12-SSR") == "8.10.0.12-SSR"


def test_snapshot_merges_debug_resolves_master_and_association() -> None:
    snapshot = parse_snapshot(snapshot_outputs())

    assert snapshot.cluster.name == "Office"
    assert snapshot.cluster.version == "8.6.0.22"
    assert snapshot.cluster.master_ap == "lobby"
    assert snapshot.cluster.ap_count == 2
    assert snapshot.cluster.client_count == 1
    assert snapshot.access_points[0].is_master is True
    assert snapshot.access_points[1].is_master is False
    assert snapshot.clients[0].associated_ap == "lobby"
    assert snapshot.clients[0].signal_strength == -55
    assert snapshot.clients[0].bssid == "aa:bb:cc:dd:ee:ff"


def test_snapshot_reflects_client_roaming() -> None:
    before = parse_snapshot(snapshot_outputs(associated_ap="192.0.2.10"))
    after_outputs = snapshot_outputs(associated_ap="192.0.2.11")
    after_outputs["show client debug"] = command_output(
        "show client debug", DEBUG_TABLE.replace("lobby", "office")
    )
    after = parse_snapshot(after_outputs)

    assert before.clients[0].associated_ap == "lobby"
    assert after.clients[0].associated_ap == "office"


def test_explicit_zero_clients_is_valid() -> None:
    clients, count = parse_clients(command_output("show clients", "0 Clients"))
    debug_clients = parse_client_debug(command_output("show client debug", "0 Clients"))

    assert clients == ()
    assert debug_clients == ()
    assert count == 0


def test_zero_client_snapshot_is_valid_and_preserves_reported_counts() -> None:
    outputs = snapshot_outputs()
    outputs["show clients"] = command_output("show clients", "0 Clients")
    outputs["show client debug"] = command_output("show client debug", "0 Clients")
    outputs["show summary"] = command_output(
        "show summary",
        "Cluster Name: Office\nMaster AP: lobby\nAccess Points: 2\nClients: 0",
    )

    snapshot = parse_snapshot(outputs)

    assert snapshot.clients == ()
    assert snapshot.cluster.client_count == 0


def test_snapshot_uses_marked_master_and_keeps_unknown_master() -> None:
    marked_outputs = snapshot_outputs()
    marked_outputs["show aps"] = command_output(
        "show aps",
        "2 Access Points\n" + APS_TABLE.replace("lobby", "lobby*", 1),
    )
    marked_outputs["show summary"] = command_output(
        "show summary", "Cluster Name: Office\nAccess Points: 2\nClients: 1"
    )
    marked = parse_snapshot(marked_outputs)
    assert marked.cluster.master_ap == "lobby"

    unknown_outputs = snapshot_outputs()
    unknown_outputs["show summary"] = command_output(
        "show summary",
        "Cluster Name: Office\nMaster AP: missing-ap\nAccess Points: 2\nClients: 1",
    )
    unknown = parse_snapshot(unknown_outputs)
    assert unknown.cluster.master_ap == "missing-ap"
    assert all(access_point.is_master is None for access_point in unknown.access_points)


def test_unmatched_debug_client_does_not_replace_authoritative_collection() -> None:
    outputs = snapshot_outputs()
    outputs["show client debug"] = command_output(
        "show client debug", DEBUG_TABLE.replace("1122.3344.5566", "aabb.ccdd.eeff")
    )

    snapshot = parse_snapshot(outputs)

    assert len(snapshot.clients) == 1
    assert snapshot.clients[0].signal_strength is None


def test_snapshot_retains_only_sanitized_raw_output() -> None:
    outputs = snapshot_outputs()
    outputs["show version"] += "sid=controller-secret\n"
    snapshot = parse_snapshot(outputs)
    raw_output = object.__getattribute__(snapshot, "_raw_output")

    assert "controller-secret" not in raw_output["show version"]
    assert "sid=<redacted>" in raw_output["show version"]


@pytest.mark.parametrize(
    ("parser", "output"),
    [
        (parse_aps, "2 Access Points\ntruncated"),
        (parse_clients, "1 Client\ntruncated"),
        (parse_client_debug, "debug output unavailable"),
        (parse_summary, "unrecognized output"),
        (parse_version, "Aruba operating system"),
    ],
)
def test_malformed_output_raises(parser: Callable[[str], object], output: str) -> None:
    with pytest.raises(ArubaInstantParseError):
        parser(output)


def test_malformed_nonzero_client_table_cannot_look_empty() -> None:
    empty_table = render_table(["MAC Address", "IP Address"], [])
    with pytest.raises(ArubaInstantParseError, match="usable client table"):
        parse_clients(command_output("show clients", f"1 Client\n{empty_table}"))

    invalid_mac_table = render_table(["MAC Address", "IP Address"], [["invalid", "192.0.2.2"]])
    with pytest.raises(ArubaInstantParseError, match="valid MAC"):
        parse_clients(invalid_mac_table)


def test_reported_count_mismatch_raises() -> None:
    with pytest.raises(ArubaInstantParseError, match="reported 3 access points"):
        parse_aps(command_output("show aps", f"3 Access Points\n{APS_TABLE}"))


def test_missing_snapshot_command_and_sanitized_diagnostics() -> None:
    with pytest.raises(ArubaInstantParseError, match="show version"):
        parse_snapshot({})

    sanitized = sanitize_output("sid=secret\r\npassword: hunter2\rpasswd=hidden")
    assert sanitized == "sid=<redacted>\npassword: <redacted>\npasswd=<redacted>"
