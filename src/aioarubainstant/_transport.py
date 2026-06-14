"""Aruba Instant HTTP transport compatibility helpers."""

from __future__ import annotations

import functools
from typing import TYPE_CHECKING, Any

from aiohttp import TCPConnector
from aiohttp.client_exceptions import ClientPayloadError
from aiohttp.client_proto import ResponseHandler
from aiohttp.helpers import DEFAULT_CHUNK_SIZE, BaseTimerContext
from aiohttp.http_parser import HttpResponseParserPy, RawResponseMessage

if TYPE_CHECKING:
    from aiohttp.streams import StreamReader


class _ArubaInstantResponseParser(HttpResponseParserPy):
    """Parse malformed Aruba response headers like aiohttp's normal mode."""

    lax = True

    def feed_data(  # type: ignore[override]
        self,
        data: bytes,
        _sep: bytes | None = None,
        *args: Any,  # noqa: ANN401
        **kwargs: Any,  # noqa: ANN401
    ) -> tuple[list[tuple[RawResponseMessage, StreamReader]], bool, bytes]:
        """Accept the bare LF tolerated by aiohttp outside debug mode."""
        return super().feed_data(data, b"\n", *args, **kwargs)


class _ArubaInstantResponseHandler(ResponseHandler):
    """Use the Aruba-compatible response parser for one connector."""

    def set_response_params(  # noqa: PLR0913
        self,
        *,
        timer: BaseTimerContext | None = None,
        skip_payload: bool = False,
        read_until_eof: bool = False,
        auto_decompress: bool = True,
        read_timeout: float | None = None,
        read_bufsize: int = DEFAULT_CHUNK_SIZE,
        timeout_ceil_threshold: float = 5,
        max_line_size: int = 8190,
        max_field_size: int = 8190,
        max_headers: int = 128,
    ) -> None:
        """Configure response parsing without changing global aiohttp mode."""
        self._skip_payload = skip_payload
        self._read_timeout = read_timeout
        self._timeout_ceil_threshold = timeout_ceil_threshold
        self._parser = _ArubaInstantResponseParser(
            self,
            self._loop,
            read_bufsize,
            timer=timer,
            payload_exception=ClientPayloadError,
            response_with_body=not skip_payload,
            read_until_eof=read_until_eof,
            auto_decompress=auto_decompress,
            max_line_size=max_line_size,
            max_field_size=max_field_size,
            max_headers=max_headers,
        )

        if self._tail:
            data, self._tail = self._tail, b""
            self.data_received(data)


class ArubaInstantTCPConnector(TCPConnector):
    """Connector scoped to Aruba Instant's malformed HTTP responses."""

    def __init__(self) -> None:
        """Initialize an Aruba-compatible connector."""
        super().__init__()
        self._factory = functools.partial(  # type: ignore[assignment]
            _ArubaInstantResponseHandler,
            loop=self._loop,
        )
