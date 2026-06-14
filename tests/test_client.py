from __future__ import annotations

import asyncio
import json
import logging
import ssl
from typing import Any, Self, cast

import aiohttp
import pytest

from aioarubainstant import (
    ArubaInstantAuthenticationError,
    ArubaInstantClient,
    ArubaInstantCommandError,
    ArubaInstantConnectionError,
    ArubaInstantNotMasterError,
    ArubaInstantParseError,
    ArubaInstantRestDisabledError,
    ArubaInstantSessionError,
    ArubaInstantTimeoutError,
    async_get_snapshot,
)
from tests.test_parsers import snapshot_outputs


class FakeResponse:
    def __init__(self, payload: object, *, status: int = 200, delay: float = 0) -> None:
        self.status = status
        self._body = payload if isinstance(payload, str) else json.dumps(payload)
        self._delay = delay

    async def __aenter__(self) -> Self:
        if self._delay:
            await asyncio.sleep(self._delay)
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def text(self) -> str:
        return self._body


class RaisingResponse:
    def __init__(self, error: BaseException) -> None:
        self._error = error

    async def __aenter__(self) -> FakeResponse:
        raise self._error

    async def __aexit__(self, *args: object) -> None:
        return None


class FakeSession:
    def __init__(self, *responses: object) -> None:
        self.responses = list(responses)
        self.requests: list[dict[str, Any]] = []
        self.closed = False

    def request(self, method: str, url: str, **kwargs: Any) -> FakeResponse | RaisingResponse:
        self.requests.append({"method": method, "url": url, **kwargs})
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            return RaisingResponse(response)
        if isinstance(response, (FakeResponse, RaisingResponse)):
            return response
        return FakeResponse(response)

    async def close(self) -> None:
        self.closed = True


def make_client(
    session: FakeSession,
    *,
    verify_ssl: bool | ssl.SSLContext = True,
    timeout: float | aiohttp.ClientTimeout = 10,
) -> ArubaInstantClient:
    return ArubaInstantClient(
        "controller.local",
        "admin",
        "secret",
        verify_ssl=verify_ssl,
        timeout=timeout,
        session=cast("aiohttp.ClientSession", session),
    )


@pytest.mark.asyncio
async def test_authentication_and_sid_reuse() -> None:
    session = FakeSession(
        {"Status": "Success", "sid": "session-one"},
        {"Status": "Success", "Status-code": 0, "Command output": "first"},
        {"Status": "Success", "Status-code": 0, "Command output": "second"},
    )
    client = make_client(session)

    assert await client.async_run_command("show aps") == "first"
    assert await client.async_run_command("show client debug") == "second"

    assert [request["url"] for request in session.requests] == [
        "https://controller.local:4343/rest/login",
        "https://controller.local:4343/rest/show-cmd",
        "https://controller.local:4343/rest/show-cmd",
    ]
    assert session.requests[1]["params"]["sid"] == "session-one"
    assert session.requests[2]["params"]["sid"] == "session-one"
    assert client.is_authenticated


@pytest.mark.asyncio
async def test_failed_authentication() -> None:
    session = FakeSession({"Status": "Failed", "Error message": "Login failed"})

    with pytest.raises(ArubaInstantAuthenticationError, match="Login failed"):
        await make_client(session).async_login()


@pytest.mark.asyncio
async def test_explicit_login_reuses_cached_sid_and_logout_without_sid_is_noop() -> None:
    session = FakeSession({"Status": "Success", "sid": "session-one"})
    client = make_client(session)

    await client.async_login()
    await client.async_login()

    assert len(session.requests) == 1
    client_without_sid = make_client(FakeSession())
    await client_without_sid.async_logout()


@pytest.mark.asyncio
async def test_missing_sid_is_authentication_failure() -> None:
    session = FakeSession({"Status": "Success"})

    with pytest.raises(ArubaInstantAuthenticationError, match="session ID"):
        await make_client(session).async_login()


@pytest.mark.asyncio
async def test_expired_sid_reauthenticates_once() -> None:
    session = FakeSession(
        {"Status": "Success", "sid": "expired"},
        {"Status-code": 1, "message": "Invalid session id or session id has expired"},
        {"Status": "Success", "sid": "fresh"},
        {"Status": "Success", "Status-code": 0, "Command output": "recovered"},
    )

    assert await make_client(session).async_run_command("show summary") == "recovered"
    login_requests = [request for request in session.requests if request["url"].endswith("login")]
    assert len(login_requests) == 2
    assert session.requests[-1]["params"]["sid"] == "fresh"


@pytest.mark.asyncio
async def test_second_expired_sid_is_not_retried() -> None:
    expired = {"Status-code": 1, "message": "Invalid session id or session id has expired"}
    session = FakeSession(
        {"Status": "Success", "sid": "first"},
        expired,
        {"Status": "Success", "sid": "second"},
        expired,
    )

    with pytest.raises(ArubaInstantSessionError):
        await make_client(session).async_run_command("show version")


@pytest.mark.asyncio
async def test_logout_clears_sid_without_closing_caller_session() -> None:
    session = FakeSession(
        {"Status": "Success", "sid": "session-one"},
        {"Status-code": 0, "message": "User logout successfully"},
    )
    client = make_client(session)

    await client.async_login()
    await client.async_close()

    assert not client.is_authenticated
    assert not session.closed
    assert session.requests[-1]["json"] == {"sid": "session-one"}


@pytest.mark.asyncio
async def test_context_manager_closes_owned_session(monkeypatch: pytest.MonkeyPatch) -> None:
    session = FakeSession(
        {"Status": "Success", "sid": "session-one"},
        {"Status-code": 0, "message": "User logout successfully"},
    )
    monkeypatch.setattr("aioarubainstant.client.ClientSession", lambda **_kwargs: session)

    async with ArubaInstantClient("controller.local", "admin", "secret") as client:
        await client.async_login()
        assert client.is_authenticated

    assert session.closed


@pytest.mark.asyncio
async def test_owned_session_accepts_aruba_malformed_response_header() -> None:
    async def handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        request = await reader.readuntil(b"\r\n\r\n")
        payload = (
            {"Status-code": 0, "message": "logout successful"}
            if b" /rest/logout " in request
            else {"Status": "Success", "sid": "session-one"}
        )
        body = json.dumps(payload).encode()
        writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\n\r\n\r\n" + body)
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    server = await asyncio.start_server(handler, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]

    async with server:
        client = ArubaInstantClient("controller.local", "admin", "secret")
        client._base_url = f"http://127.0.0.1:{port}"  # noqa: SLF001
        async with client:
            await client.async_login()
            assert client.is_authenticated

    assert not client.is_authenticated


@pytest.mark.asyncio
async def test_cleanup_closes_owned_session_when_logout_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = FakeSession(
        {"Status": "Success", "sid": "session-one"},
        {"Status-code": 7, "message": "logout failed"},
    )
    monkeypatch.setattr("aioarubainstant.client.ClientSession", lambda **_kwargs: session)
    client = ArubaInstantClient("controller.local", "admin", "secret")
    await client.async_login()

    with pytest.raises(ArubaInstantSessionError, match="logout failed"):
        await client.async_close()

    assert session.closed


@pytest.mark.asyncio
@pytest.mark.parametrize("verify_ssl", [True, False, ssl.create_default_context()])
async def test_tls_verification_setting_is_forwarded(verify_ssl: bool | ssl.SSLContext) -> None:
    session = FakeSession({"Status": "Success", "sid": "session-one"})

    await make_client(session, verify_ssl=verify_ssl).async_login()

    assert session.requests[0]["ssl"] is verify_ssl


@pytest.mark.asyncio
async def test_client_timeout_object_is_forwarded() -> None:
    timeout = aiohttp.ClientTimeout(total=42)
    session = FakeSession({"Status": "Success", "sid": "session-one"})

    await make_client(session, timeout=timeout).async_login()

    assert session.requests[0]["timeout"] is timeout


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (TimeoutError(), ArubaInstantTimeoutError),
        (aiohttp.ClientConnectionError(), ArubaInstantConnectionError),
    ],
)
async def test_transport_errors(error: BaseException, expected: type[BaseException]) -> None:
    with pytest.raises(expected):
        await make_client(FakeSession(error)).async_login()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("response", "expected"),
    [
        ("REST API Service is not enabled", ArubaInstantRestDisabledError),
        (
            "REST API service is available only on the master Instant AP.",
            ArubaInstantNotMasterError,
        ),
    ],
)
async def test_controller_service_errors(response: str, expected: type[BaseException]) -> None:
    with pytest.raises(expected):
        await make_client(FakeSession(response)).async_login()


@pytest.mark.asyncio
async def test_command_failure_and_malformed_response() -> None:
    command_failure = FakeSession(
        {"Status": "Success", "sid": "session-one"},
        {"Status": "Failed", "Status-code": 6, "Error message": "Parse error"},
    )
    with pytest.raises(ArubaInstantCommandError, match="Parse error"):
        await make_client(command_failure).async_run_command("show aps")

    malformed = FakeSession("not-json")
    with pytest.raises(ArubaInstantParseError, match="malformed JSON"):
        await make_client(malformed).async_login()

    unsupported_json = FakeSession(["not", "an", "object"])
    with pytest.raises(ArubaInstantParseError, match="unsupported JSON"):
        await make_client(unsupported_json).async_login()


@pytest.mark.asyncio
async def test_command_without_output_is_malformed() -> None:
    session = FakeSession(
        {"Status": "Success", "sid": "session-one"},
        {"Status": "Success", "Status-code": 0},
    )

    with pytest.raises(ArubaInstantParseError, match="did not contain command output"):
        await make_client(session).async_run_command("show aps")


@pytest.mark.asyncio
async def test_commands_are_serialized() -> None:
    session = FakeSession(
        {"Status": "Success", "sid": "session-one"},
        FakeResponse({"Status": "Success", "Status-code": 0, "Command output": "one"}, delay=0.01),
        {"Status": "Success", "Status-code": 0, "Command output": "two"},
    )
    client = make_client(session)

    results = await asyncio.gather(
        client.async_run_command("show aps"), client.async_run_command("show client debug")
    )
    assert tuple(results) == ("one", "two")


@pytest.mark.asyncio
async def test_unsupported_command_and_invalid_hosts() -> None:
    client = make_client(FakeSession())
    with pytest.raises(ValueError, match="Unsupported"):
        await client.async_run_command("show running-config")
    with pytest.raises(ValueError, match="Unsupported"):
        await client.async_run_command("show clients")

    with pytest.raises(ValueError, match="hostname"):
        ArubaInstantClient("http://controller.local", "admin", "secret")
    with pytest.raises(ValueError, match="path"):
        ArubaInstantClient("https://controller.local/rest", "admin", "secret")


@pytest.mark.asyncio
async def test_https_url_port_ipv6_and_target() -> None:
    session = FakeSession(
        {"Status": "Success", "sid": "session-one"},
        {"Status": "Success", "Status-code": 0, "Command output": "ok"},
    )
    client = ArubaInstantClient(
        "https://[2001:db8::1]:4443",
        "admin",
        "secret",
        session=cast("aiohttp.ClientSession", session),
    )

    assert await client.async_run_command("show aps", target="192.0.2.4") == "ok"
    assert session.requests[0]["url"] == "https://[2001:db8::1]:4443/rest/login"
    assert session.requests[1]["params"]["iap_ip_addr"] == "192.0.2.4"


@pytest.mark.asyncio
async def test_closed_caller_session_is_rejected() -> None:
    session = FakeSession()
    session.closed = True

    with pytest.raises(ArubaInstantConnectionError, match="caller-provided"):
        await make_client(session).async_login()


@pytest.mark.asyncio
async def test_http_authentication_and_command_errors() -> None:
    with pytest.raises(ArubaInstantAuthenticationError, match="HTTP 401"):
        await make_client(FakeSession(FakeResponse({}, status=401))).async_login()

    session = FakeSession(
        {"Status": "Success", "sid": "session-one"},
        FakeResponse({"message": "server error"}, status=500),
    )
    with pytest.raises(ArubaInstantCommandError, match="server error"):
        await make_client(session).async_run_command("show aps")

    with pytest.raises(ArubaInstantAuthenticationError, match="HTTP 401"):
        await make_client(FakeSession(FakeResponse("Unauthorized", status=401))).async_login()

    plain_command_error = FakeSession(
        {"Status": "Success", "sid": "session-one"},
        FakeResponse("Internal Server Error", status=500),
    )
    with pytest.raises(ArubaInstantCommandError, match="HTTP 500"):
        await make_client(plain_command_error).async_run_command("show aps")


@pytest.mark.asyncio
async def test_logout_http_and_string_status_errors() -> None:
    http_error = FakeSession(
        {"Status": "Success", "sid": "session-one"},
        FakeResponse({}, status=500),
    )
    client = make_client(http_error)
    await client.async_login()
    with pytest.raises(ArubaInstantConnectionError, match="HTTP 500"):
        await client.async_logout()

    command_error = FakeSession(
        {"Status": "Success", "sid": "session-one"},
        {"Status": "Failed", "Status-code": "6", "message": "string status"},
    )
    with pytest.raises(ArubaInstantCommandError, match="string status"):
        await make_client(command_error).async_run_command("show aps")


@pytest.mark.asyncio
async def test_public_snapshot_convenience_function() -> None:
    outputs = snapshot_outputs()
    session = FakeSession(
        {"Status": "Success", "sid": "session-one"},
        *(
            {"Status": "Success", "Status-code": 0, "Command output": outputs[command]}
            for command in sorted(outputs)
        ),
        {"Status-code": 0, "message": "User logout successfully"},
    )

    snapshot = await async_get_snapshot(
        "controller.local",
        "admin",
        "secret",
        session=cast("aiohttp.ClientSession", session),
    )

    assert snapshot.cluster.name == "Office"
    assert snapshot.clients[0].hostname == "phone"
    assert {
        request["params"]["cmd"]
        for request in session.requests
        if request["url"].endswith("show-cmd")
    } == {"show aps", "show client debug", "show summary", "show version"}
    assert not session.closed


@pytest.mark.asyncio
async def test_password_and_sid_are_never_logged(caplog: pytest.LogCaptureFixture) -> None:
    session = FakeSession(
        {"Status": "Success", "sid": "session-one"},
        {"Status": "Success", "Status-code": 0, "Command output": "safe output"},
        {"Status-code": 0, "message": "User logout successfully"},
    )
    client = make_client(session)

    with caplog.at_level(logging.DEBUG):
        await client.async_run_command("show version")
        await client.async_logout()

    assert "secret" not in caplog.text
    assert "session-one" not in caplog.text
