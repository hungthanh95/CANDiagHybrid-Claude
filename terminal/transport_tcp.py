"""Option A transport: plain TCP, line-based proto=1 framing.

Connects to a CAPL TCP transport node (or, for M1, :class:`mock_ecu.server.MockServer`)
on ``host:port`` and exchanges newline-terminated protocol lines.

Reconnection (FR-16) is intentionally out of scope for M1 -- it lands in M6
hardening. A connection drop surfaces as :class:`TransportError` from
:meth:`TcpTransport.send` or via the :meth:`TcpTransport.recv_lines`
async iterator ending (StopAsyncIteration) combined with
:attr:`TcpTransport.closed` becoming true; callers that need to distinguish
"clean BYE-initiated close" from "unexpected drop" should track that
themselves in M1.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator

from protocol.wire import MAX_LINE

logger = logging.getLogger(__name__)


class TransportError(Exception):
    """Raised when the TCP connection is unavailable or drops unexpectedly."""


class TcpTransport:
    """Async line-based TCP transport for the proto=1 wire protocol.

    Args:
        host: Server hostname/IP (default ``127.0.0.1``).
        port: Server TCP port (default ``9000``).
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 9000) -> None:
        self.host = host
        self.port = port
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self.closed = False

    async def connect(self) -> None:
        """Open the TCP connection.

        Raises:
            TransportError: if the connection cannot be established.
        """
        try:
            self._reader, self._writer = await asyncio.open_connection(self.host, self.port)
        except OSError as exc:
            raise TransportError(f"connect to {self.host}:{self.port} failed: {exc}") from exc
        self.closed = False
        logger.debug("connected to %s:%d", self.host, self.port)

    async def send(self, line: str) -> None:
        """Send one protocol line (newline appended if missing).

        Raises:
            TransportError: if not connected or the write fails.
        """
        if self._writer is None or self.closed:
            raise TransportError("not connected")
        if not line.endswith("\n"):
            line += "\n"
        if len(line) > MAX_LINE:
            raise TransportError(f"line exceeds MAX_LINE ({MAX_LINE}): {len(line)}")
        try:
            self._writer.write(line.encode("ascii"))
            await self._writer.drain()
        except OSError as exc:
            self.closed = True
            raise TransportError(f"send failed: {exc}") from exc
        logger.debug("-> %s", line.rstrip("\n"))

    async def recv_lines(self) -> AsyncIterator[str]:
        """Yield decoded protocol lines (without trailing newline) as they arrive.

        Ends (the async generator returns) when the peer closes the
        connection cleanly. Raises :class:`TransportError` on an
        unexpected I/O error or an oversized line.
        """
        if self._reader is None:
            raise TransportError("not connected")
        while True:
            try:
                raw = await self._reader.readuntil(b"\n")
            except asyncio.IncompleteReadError as exc:
                if exc.partial:
                    logger.debug("connection closed with partial data: %r", exc.partial)
                self.closed = True
                return
            except asyncio.LimitOverrunError as exc:
                self.closed = True
                raise TransportError("line exceeds buffer limit") from exc
            except OSError as exc:
                self.closed = True
                raise TransportError(f"recv failed: {exc}") from exc

            line = raw.decode("ascii", errors="replace").rstrip("\r\n")
            logger.debug("<- %s", line)
            yield line

    async def close(self) -> None:
        """Close the connection (idempotent)."""
        if self._writer is not None and not self.closed:
            self._writer.close()
        self.closed = True
