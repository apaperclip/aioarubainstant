"""Asynchronous transport for Aruba Instant controllers."""

from __future__ import annotations

import json
import ssl
from asyncio import Lock
from typing import TYPE_CHECKING, Self
from urllib.parse import urlsplit

from aiohttp import ClientError, ClientSession, ClientTimeout

from .exceptions import (
    ArubaInstantAuthenticationError,
    ArubaInstantCommandError,
    ArubaInstantConnectionError,
    ArubaInstantNotMasterError,
    ArubaInstantParseError,
    ArubaInstantRestDisabledError,
    ArubaInstantSessionError,
    ArubaInstantTimeoutError,
)
from .parsers import parse_snapshot

DEFAULT_PORT = 4343
DEFAULT_TIMEOUT = 10.0
SUPPORTED_COMMANDS = frozenset(
    {
        "show aps",
        "show client debug",
        "show clients",
        "show summary",
        "show version",
    }
)

JsonObject = dict[str, object]
VerifySSL = bool | ssl.SSLContext

HTTP_BAD_REQUEST = 400

if TYPE_CHECKING:
    from collections.abc import Mapping
    from types import TracebackType

    from .models import ArubaInstantSnapshot


class ArubaInstantClient:
    """Asynchronous client for an Aruba Instant controller."""

    def __init__(  # noqa: PLR0913
        self,
        host: str,
        username: str,
        password: str,
        *,
        port: int = DEFAULT_PORT,
        verify_ssl: VerifySSL = True,
        timeout: float | ClientTimeout = DEFAULT_TIMEOUT,
        session: ClientSession | None = None,
    ) -> None:
        """Initialize a client without performing network I/O."""
        self._base_url, self._address = _normalize_controller(host, port)
        self._username = username
        self._password = password
        self._verify_ssl = verify_ssl
        self._timeout = (
            timeout if isinstance(timeout, ClientTimeout) else ClientTimeout(total=timeout)
        )
        self._session = session
        self._owns_session = session is None
        self._sid: str | None = None
        self._command_lock = Lock()

    @property
    def is_authenticated(self) -> bool:
        """Return whether the client currently has a cached session ID."""
        return self._sid is not None

    async def __aenter__(self) -> Self:
        """Enter the asynchronous context manager."""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Log out and close owned resources."""
        await self.async_close()

    async def async_login(self) -> None:
        """Authenticate unless a reusable SID is already cached."""
        async with self._command_lock:
            if self._sid is None:
                await self._async_login_unlocked()

    async def async_logout(self) -> None:
        """Log out the cached controller session."""
        async with self._command_lock:
            await self._async_logout_unlocked()

    async def async_run_command(self, command: str, *, target: str | None = None) -> str:
        """Run one supported monitoring command with one session retry."""
        if command not in SUPPORTED_COMMANDS:
            msg = f"Unsupported monitoring command: {command}"
            raise ValueError(msg)

        async with self._command_lock:
            return await self._async_run_command_with_retry_unlocked(command, target=target)

    async def async_get_snapshot(self) -> ArubaInstantSnapshot:
        """Collect and parse a coherent monitoring snapshot."""
        async with self._command_lock:
            outputs = {
                command: await self._async_run_command_with_retry_unlocked(command, target=None)
                for command in sorted(SUPPORTED_COMMANDS)
            }
        return parse_snapshot(outputs)

    async def async_close(self) -> None:
        """Log out and close the internally created HTTP session."""
        error: Exception | None = None
        try:
            await self.async_logout()
        except Exception as err:  # noqa: BLE001  # Cleanup must still close an owned session.
            error = err
        finally:
            if self._owns_session and self._session is not None and not self._session.closed:
                await self._session.close()

        if error is not None:
            raise error

    async def _async_login_unlocked(self) -> None:
        payload = await self._request_json(
            "POST",
            "/rest/login",
            json_data={"user": self._username, "passwd": self._password},
            operation="login",
        )
        _raise_controller_error(payload, operation="login")

        sid = payload.get("sid")
        if not isinstance(sid, str) or not sid:
            msg = _response_message(payload) or "Controller did not return a session ID"
            raise ArubaInstantAuthenticationError(msg)
        self._sid = sid

    async def _async_logout_unlocked(self) -> None:
        sid = self._sid
        self._sid = None
        if sid is None:
            return

        payload = await self._request_json(
            "POST",
            "/rest/logout",
            json_data={"sid": sid},
            operation="logout",
        )
        _raise_controller_error(payload, operation="logout")

    async def _async_run_command_unlocked(self, command: str, *, target: str | None) -> str:
        if self._sid is None:
            msg = "A controller session is required"
            raise ArubaInstantSessionError(msg)

        payload = await self._request_json(
            "GET",
            "/rest/show-cmd",
            params={
                "iap_ip_addr": target or self._address,
                "cmd": command,
                "sid": self._sid,
            },
            operation="command",
        )
        _raise_controller_error(payload, operation="command")

        output = payload.get("Command output")
        if not isinstance(output, str):
            msg = f"Controller response for {command!r} did not contain command output"
            raise ArubaInstantParseError(msg)
        return output

    async def _async_run_command_with_retry_unlocked(
        self, command: str, *, target: str | None
    ) -> str:
        if self._sid is None:
            await self._async_login_unlocked()
        try:
            return await self._async_run_command_unlocked(command, target=target)
        except ArubaInstantSessionError:
            self._sid = None
            await self._async_login_unlocked()
            return await self._async_run_command_unlocked(command, target=target)

    async def _request_json(
        self,
        method: str,
        path: str,
        *,
        operation: str,
        params: Mapping[str, str] | None = None,
        json_data: Mapping[str, str] | None = None,
    ) -> JsonObject:
        session = self._get_session()
        try:
            async with session.request(
                method,
                f"{self._base_url}{path}",
                params=params,
                json=json_data,
                ssl=self._verify_ssl,
                timeout=self._timeout,
            ) as response:
                body = await response.text()
                status = response.status
        except TimeoutError as err:
            msg = f"Timed out communicating with {self._address}"
            raise ArubaInstantTimeoutError(msg) from err
        except ClientError as err:
            msg = f"Could not communicate with {self._address}"
            raise ArubaInstantConnectionError(msg) from err

        _raise_text_error(body)
        try:
            payload = json.loads(body)
        except (json.JSONDecodeError, TypeError) as err:
            msg = f"Controller returned malformed JSON during {operation}"
            raise ArubaInstantParseError(msg) from err

        if not isinstance(payload, dict) or not all(isinstance(key, str) for key in payload):
            msg = f"Controller returned unsupported JSON during {operation}"
            raise ArubaInstantParseError(msg)

        result = dict(payload)
        if status >= HTTP_BAD_REQUEST:
            message = _response_message(result) or f"Controller returned HTTP {status}"
            if operation == "login" and status in {401, 403}:
                raise ArubaInstantAuthenticationError(message)
            if operation == "command":
                raise ArubaInstantCommandError(message)
            raise ArubaInstantConnectionError(message)
        return result

    def _get_session(self) -> ClientSession:
        if self._session is None or self._session.closed:
            if not self._owns_session:
                msg = "The caller-provided aiohttp session is closed"
                raise ArubaInstantConnectionError(msg)
            self._session = ClientSession()
        return self._session


def _normalize_controller(host: str, port: int) -> tuple[str, str]:
    candidate = host if "://" in host else f"https://{host}"
    parsed = urlsplit(candidate)
    if parsed.scheme != "https" or parsed.hostname is None:
        msg = "Controller host must be a hostname, IP address, or HTTPS URL"
        raise ValueError(msg)
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        msg = "Controller URL must not contain a path, query, or fragment"
        raise ValueError(msg)

    address = parsed.hostname
    effective_port = parsed.port or port
    url_address = f"[{address}]" if ":" in address else address
    return f"https://{url_address}:{effective_port}", address


def _status_code(payload: Mapping[str, object]) -> int | None:
    value = payload.get("Status-code", payload.get("Status"))
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _response_message(payload: Mapping[str, object]) -> str | None:
    for key in ("Error message", "message", "Message"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _raise_text_error(text: str) -> None:
    lowered = text.casefold()
    if "rest api service is not enabled" in lowered:
        msg = "REST API service is not enabled"
        raise ArubaInstantRestDisabledError(msg)
    if "rest api service is available only on the master" in lowered:
        msg = "REST API service is available only on the master AP"
        raise ArubaInstantNotMasterError(msg)


def _raise_controller_error(payload: Mapping[str, object], *, operation: str) -> None:
    message = _response_message(payload)
    if message is not None:
        _raise_text_error(message)
    lowered = message.casefold() if message is not None else ""
    code = _status_code(payload)
    status = payload.get("Status")
    failed = isinstance(status, str) and status.casefold() == "failed"

    if code == 1 or "invalid session id" in lowered or "session id has expired" in lowered:
        raise ArubaInstantSessionError(message or "Invalid or expired controller session")
    if operation == "login" and (failed or code not in {None, 0}):
        raise ArubaInstantAuthenticationError(message or "Controller authentication failed")
    if operation == "command" and (failed or code not in {None, 0}):
        raise ArubaInstantCommandError(message or "Controller command failed")
    if operation == "logout" and code not in {None, 0}:
        raise ArubaInstantSessionError(message or "Controller logout failed")


async def async_get_snapshot(  # noqa: PLR0913
    host: str,
    username: str,
    password: str,
    *,
    port: int = DEFAULT_PORT,
    verify_ssl: VerifySSL = True,
    timeout: float | ClientTimeout = DEFAULT_TIMEOUT,  # noqa: ASYNC109
    session: ClientSession | None = None,
) -> ArubaInstantSnapshot:
    """Collect one snapshot with a short-lived client."""
    async with ArubaInstantClient(
        host,
        username,
        password,
        port=port,
        verify_ssl=verify_ssl,
        timeout=timeout,
        session=session,
    ) as client:
        return await client.async_get_snapshot()
