"""Exceptions raised by aioarubainstant."""

from __future__ import annotations


class ArubaInstantError(Exception):
    """Base exception for all aioarubainstant errors."""


class ArubaInstantAuthenticationError(ArubaInstantError):
    """Authentication with the controller failed."""


class ArubaInstantConnectionError(ArubaInstantError):
    """The controller could not be reached."""


class ArubaInstantTimeoutError(ArubaInstantConnectionError):
    """Communication with the controller timed out."""


class ArubaInstantRestDisabledError(ArubaInstantError):
    """The REST API is disabled on the controller."""


class ArubaInstantNotMasterError(ArubaInstantError):
    """The request was sent to a non-master access point."""


class ArubaInstantSessionError(ArubaInstantAuthenticationError):
    """The controller rejected an invalid or expired session."""


class ArubaInstantCommandError(ArubaInstantError):
    """The controller failed to execute a monitoring command."""


class ArubaInstantParseError(ArubaInstantError):
    """Controller output is malformed or unsupported."""
