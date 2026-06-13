"""Normalized Aruba Instant monitoring models."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping


@dataclass(frozen=True, slots=True)
class ArubaCluster:
    """Cluster-level information reported by the controller."""

    name: str | None = None
    management_address: str | None = None
    version: str | None = None
    master_ap: str | None = None
    ap_count: int | None = None
    client_count: int | None = None


@dataclass(frozen=True, slots=True)
class ArubaAccessPoint:
    """An access point in the Aruba Instant cluster."""

    mac: str | None = None
    name: str | None = None
    ip_address: str | None = None
    model: str | None = None
    serial: str | None = None
    firmware: str | None = None
    connected_clients: int | None = None
    is_master: bool | None = None


@dataclass(frozen=True, slots=True)
class ArubaClient:
    """A wireless client associated with the cluster."""

    mac: str
    hostname: str | None = None
    ip_address: str | None = None
    ssid: str | None = None
    bssid: str | None = None
    associated_ap: str | None = None
    signal_strength: int | None = None
    link_speed: int | None = None
    channel: int | None = None
    phy_mode: str | None = None
    role: str | None = None


@dataclass(frozen=True, slots=True)
class ArubaInstantSnapshot:
    """A coherent monitoring snapshot from an Aruba Instant cluster."""

    cluster: ArubaCluster
    access_points: tuple[ArubaAccessPoint, ...]
    clients: tuple[ArubaClient, ...]
    _raw_output: Mapping[str, str]

    def __post_init__(self) -> None:
        """Protect retained diagnostic output from mutation."""
        object.__setattr__(self, "_raw_output", MappingProxyType(dict(self._raw_output)))
