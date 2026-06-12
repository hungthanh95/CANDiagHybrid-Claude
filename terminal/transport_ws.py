"""Option B transport: WebSocket, line-based proto=1 framing.

Connects to the Python bridge (``bridge/flexdiag_bridge.py``) at
``ws://host:port/`` and exchanges newline-free protocol lines (the
``websockets`` library delivers one text message per ``send``/iteration; the
bridge sends one protocol line per message, matching the TCP transport's
one-line-per-read framing).

Mirrors :class:`terminal.transport_tcp.TcpTransport`'s public surface
exactly (``connect``, ``send``, ``recv_lines``, ``close``, ``closed``,
``TransportError``) so :class:`terminal.repl.Repl` can use either transport
with no changes to its command-dispatch/render logic (CLAUDE.md rule 4).
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator

from protocol.wire import MAX_LINE
from terminal.transport_tcp import TransportError

logger = logging.getLogger(__name__)

__all__ = ["TransportError", "WsTransport"]


class WsTransport:
    """Async line-based WebSocket transport for the proto=1 wire protocol.

    Args:
        host: Server hostname/IP (default ``127.0.0.1``).
        port: Server WebSocket port (default ``8770``, per CLAUDE.md §5).
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 8770) -> None:
        self.host = host
        self.port = port
        self._ws: object | None = None
        self.closed = False

    async def connect(self) -> None:
        """Open the WebSocket connection.

        Raises:
            TransportError: if the connection cannot be established.
        """
        import websockets

        uri = f"ws://{self.host}:{self.port}/"
        try:
            self._ws = await websockets.connect(uri, max_size=MAX_LINE + 64)
        except (OSError, websockets.exceptions.WebSocketException) as exc:
            raise TransportError(f"connect to {uri} failed: {exc}") from exc
        self.closed = False
        logger.debug("connected to %s", uri)

    async def send(self, line: str) -> None:
        """Send one protocol line (trailing newline stripped before send).

        Raises:
            TransportError: if not connected or the send fails.
        """
        import websockets

        if self._ws is None or self.closed:
            raise TransportError("not connected")
        if line.endswith("\n"):
            line = line[:-1]
        if len(line) + 1 > MAX_LINE:
            raise TransportError(f"line exceeds MAX_LINE ({MAX_LINE}): {len(line) + 1}")
        try:
            await self._ws.send(line)  # type: ignore[attr-defined]
        except (OSError, websockets.exceptions.WebSocketException) as exc:
            self.closed = True
            raise TransportError(f"send failed: {exc}") from exc
        logger.debug("-> %s", line)

    async def recv_lines(self) -> AsyncIterator[str]:
        """Yield decoded protocol lines (without trailing newline) as they arrive.

        Ends (the async generator returns) when the peer closes the
        connection cleanly. Raises :class:`TransportError` on an
        unexpected I/O error or an oversized message.
        """
        import websockets

        if self._ws is None:
            raise TransportError("not connected")
        try:
            async for raw in self._ws:  # type: ignore[union-attr]
                if isinstance(raw, bytes):
                    line = raw.decode("ascii", errors="replace")
                else:
                    line = raw
                line = line.rstrip("\r\n")
                if len(line) + 1 > MAX_LINE:
                    self.closed = True
                    raise TransportError("line exceeds buffer limit")
                logger.debug("<- %s", line)
                yield line
        except websockets.exceptions.ConnectionClosedOK:
            self.closed = True
            return
        except websockets.exceptions.ConnectionClosedError as exc:
            self.closed = True
            raise TransportError(f"recv failed: {exc}") from exc
        finally:
            self.closed = True

    async def close(self) -> None:
        """Close the connection (idempotent)."""
        if self._ws is not None and not self.closed:
            await self._ws.close()  # type: ignore[attr-defined]
        self.closed = True
