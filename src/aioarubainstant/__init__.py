"""Asynchronous client for the Aruba Instant REST API."""

from __future__ import annotations

from .client import ArubaInstantClient, async_get_snapshot
from .exceptions import (
    ArubaInstantAuthenticationError,
    ArubaInstantCommandError,
    ArubaInstantConnectionError,
    ArubaInstantError,
    ArubaInstantNotMasterError,
    ArubaInstantParseError,
    ArubaInstantRestDisabledError,
    ArubaInstantSessionError,
    ArubaInstantTimeoutError,
)
from .models import ArubaAccessPoint, ArubaClient, ArubaCluster, ArubaInstantSnapshot

__all__ = [
    "ArubaAccessPoint",
    "ArubaClient",
    "ArubaCluster",
    "ArubaInstantAuthenticationError",
    "ArubaInstantClient",
    "ArubaInstantCommandError",
    "ArubaInstantConnectionError",
    "ArubaInstantError",
    "ArubaInstantNotMasterError",
    "ArubaInstantParseError",
    "ArubaInstantRestDisabledError",
    "ArubaInstantSessionError",
    "ArubaInstantSnapshot",
    "ArubaInstantTimeoutError",
    "async_get_snapshot",
]

__version__ = "0.1.4"
