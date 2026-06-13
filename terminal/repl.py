"""Interactive REPL for the FlexDiag terminal client (proto=1, Option B).

Commands map 1:1 to protocol verbs plus conveniences (``docs/03`` §8):

- ``connectb [host] [port]`` -- Option B (WebSocket bridge), default
  ``127.0.0.1 8770``.
- ``readdtc [mask_hex]``
- ``cleardtc``
- ``session <hex>``
- ``sec <level_hex>`` (alias ``security``)
- ``tp on`` / ``tp off``
- ``raw <hex bytes>`` e.g. ``raw 22 F1 90``
- ``ping``
- ``bye``
- ``trace on`` / ``trace off`` -- toggles line-level wire logging to stderr.
- ``quit``

Each command sends the corresponding wire-protocol line, waits for the
terminal response carrying the matching ``seq`` (skipping unsolicited
``seq=0`` lines such as ``READY``/``EVT``), and renders it. ``RSP`` after
``READDTC`` is decoded via :mod:`protocol.dtc`; ``NRC`` is annotated via
:mod:`protocol.nrc`.

Reconnection (FR-16, NFR-5): on transport loss, any in-flight requests are
failed immediately with :class:`terminal.transport_ws.TransportError`
(rather than waiting for the per-request timeout), and the REPL then
attempts a bounded, exponentially-backed-off reconnect per
:class:`ReconnectPolicy`. If reconnection succeeds, the connection resumes
transparently. If all attempts are exhausted, the REPL ends up cleanly
disconnected (``self.transport is None``) -- no hang, no crash.
"""

from __future__ import annotations

import asyncio
import dataclasses
import logging
import sys

from protocol.dtc import parse_read_dtc_payload
from protocol.nrc import nrc_name
from protocol.wire import (
    ProtocolError,
    Response,
    SeqAllocator,
    Verb,
    bytes_to_hex,
    hex_to_bytes,
    parse_response,
)
from terminal.transport_ws import TransportError, WsTransport

logger = logging.getLogger(__name__)


@dataclasses.dataclass(frozen=True)
class ReconnectPolicy:
    """Bounded exponential-backoff policy for auto-reconnection (FR-16).

    Args:
        max_attempts: Maximum number of reconnect attempts after a transport
            drop. ``0`` disables auto-reconnect entirely.
        base_delay: Delay (seconds) before the first reconnect attempt.
            Subsequent attempts double this delay (``base_delay * 2**k``),
            capped at ``max_delay``.
        max_delay: Upper bound (seconds) on the backoff delay between
            attempts.
    """

    max_attempts: int = 5
    base_delay: float = 0.5
    max_delay: float = 10.0

    def delay_for(self, attempt: int) -> float:
        """Backoff delay (seconds) before reconnect ``attempt`` (0-indexed)."""
        return min(self.base_delay * (2**attempt), self.max_delay)


class Repl:
    """Holds connection/session state for the interactive terminal."""

    def __init__(self, reconnect: ReconnectPolicy | None = None) -> None:
        self.transport: WsTransport | None = None
        self.seq_alloc = SeqAllocator()
        self.trace = False
        self.reconnect = reconnect if reconnect is not None else ReconnectPolicy()
        self._reader_task: asyncio.Task[None] | None = None
        self._pending: dict[int, asyncio.Future[Response]] = {}
        self._host: str | None = None
        self._port: int | None = None
        # Set while a reconnect attempt sequence is in progress, so
        # disconnect() (and a second drop) don't race with it.
        self._reconnecting = False

    # ------------------------------------------------------------------
    # connection management
    # ------------------------------------------------------------------

    async def connectb(self, host: str = "127.0.0.1", port: int = 8770) -> None:
        if self.transport is not None:
            await self.disconnect()
        transport = WsTransport(host, port)
        await transport.connect()
        self.transport = transport
        self._host = host
        self._port = port
        self._reader_task = asyncio.create_task(self._read_loop())
        print(f"connected (Option B) to {host}:{port}")

    async def disconnect(self) -> None:
        self._host = None
        self._port = None
        self._reconnecting = False
        if self.transport is not None:
            await self.transport.close()
        if self._reader_task is not None:
            self._reader_task.cancel()
            self._reader_task = None
        self.transport = None
        # Fail any commands still waiting for a response.
        self._fail_pending("connection closed")

    def _fail_pending(self, message: str) -> None:
        for fut in self._pending.values():
            if not fut.done():
                fut.set_exception(TransportError(message))
        self._pending.clear()

    async def _read_loop(self) -> None:
        assert self.transport is not None
        try:
            async for line in self.transport.recv_lines():
                if self.trace:
                    print(f"<- {line}", file=sys.stderr)
                try:
                    resp = parse_response(line)
                except ProtocolError as exc:
                    logger.warning("unparseable line from server: %r (%s)", line, exc)
                    continue
                if resp.seq == 0:
                    # Unsolicited READY/EVT -- not correlated to a command.
                    if not self.trace:
                        self._print_unsolicited(resp)
                    continue
                fut = self._pending.pop(resp.seq, None)
                if fut is not None and not fut.done():
                    fut.set_result(resp)
                else:
                    logger.warning("response with no matching request: %r", line)
        except TransportError as exc:
            logger.error("transport error: %s", exc)
        finally:
            # FR-16: fail any in-flight requests immediately on transport
            # loss, before attempting (bounded) reconnection.
            self._fail_pending("connection closed")
            await self._try_reconnect()

    async def _try_reconnect(self) -> None:
        """Attempt bounded, exponentially-backed-off reconnection (FR-16).

        Runs after the read loop ends (transport drop). On success, installs
        a fresh transport and restarts the read loop. On exhaustion (or if
        auto-reconnect is disabled / no host:port to reconnect to), leaves
        ``self.transport`` as ``None`` -- cleanly disconnected, no hang.
        """
        if self._reconnecting:
            return
        host, port = self._host, self._port
        old_transport = self.transport
        self.transport = None
        self._reader_task = None
        if old_transport is not None:
            await old_transport.close()
        if host is None or port is None or self.reconnect.max_attempts <= 0:
            return

        self._reconnecting = True
        try:
            for attempt in range(self.reconnect.max_attempts):
                await asyncio.sleep(self.reconnect.delay_for(attempt))
                # disconnect() may have been called while we were sleeping.
                if self._host is None:
                    return
                transport = WsTransport(host, port)
                try:
                    await transport.connect()
                except TransportError as exc:
                    logger.warning(
                        "reconnect attempt %d/%d to %s:%s failed: %s",
                        attempt + 1,
                        self.reconnect.max_attempts,
                        host,
                        port,
                        exc,
                    )
                    continue
                self.transport = transport
                self._reader_task = asyncio.create_task(self._read_loop())
                logger.info("reconnected to %s:%s", host, port)
                return
            logger.error(
                "reconnect exhausted after %d attempts; staying disconnected",
                self.reconnect.max_attempts,
            )
        finally:
            self._reconnecting = False

    @staticmethod
    def _print_unsolicited(resp: Response) -> None:
        if resp.verb == Verb.READY.value:
            print(f"[banner] READY proto={resp.proto} tool={resp.tool} transport={resp.transport}")
        else:
            print(f"[unsolicited] {resp.verb} {resp.args}")

    # ------------------------------------------------------------------
    # request/response correlation
    # ------------------------------------------------------------------

    async def _send_and_wait(self, line: str, timeout: float = 5.0) -> Response:
        if self.transport is None:
            raise TransportError("not connected")
        seq = int(line.split()[0])
        fut: asyncio.Future[Response] = asyncio.get_event_loop().create_future()
        self._pending[seq] = fut
        if self.trace:
            print(f"-> {line}", file=sys.stderr)
        await self.transport.send(line)
        try:
            return await asyncio.wait_for(fut, timeout=timeout)
        except asyncio.TimeoutError as exc:
            self._pending.pop(seq, None)
            raise TransportError(f"timed out waiting for response to: {line!r}") from exc

    # ------------------------------------------------------------------
    # rendering
    # ------------------------------------------------------------------

    def render(self, resp: Response) -> str:
        if resp.verb == Verb.RSP.value:
            assert resp.data is not None
            return f"RSP {bytes_to_hex(resp.data)}"
        if resp.verb == Verb.NRC.value:
            assert resp.sid is not None and resp.nrc is not None
            name = nrc_name(resp.nrc)
            return f"NRC {resp.sid:02X} {resp.nrc:02X} ({name})"
        if resp.verb == Verb.OK.value:
            if resp.kind == "TP":
                return "OK TP"
            return f"OK SEC {resp.level:02X}"
        if resp.verb == Verb.ERR.value:
            return f"ERR {resp.code} {resp.text}"
        if resp.verb == Verb.PONG.value:
            return "PONG"
        return f"{resp.verb} {resp.args}"

    def render_readdtc(self, resp: Response) -> str:
        if resp.verb != Verb.RSP.value or resp.data is None:
            return self.render(resp)
        try:
            _mask, dtcs = parse_read_dtc_payload(resp.data)
        except ValueError:
            return self.render(resp)
        if not dtcs:
            return "RSP " + bytes_to_hex(resp.data) + "\n(no DTCs)"
        lines = ["RSP " + bytes_to_hex(resp.data)]
        for dtc in dtcs:
            lines.append(f"  {dtc.code} (status=0x{dtc.status:02X})")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # command dispatch
    # ------------------------------------------------------------------

    async def run_command(self, text: str) -> Response | None:
        """Run one REPL command line. Returns the server Response, if any.

        Returns ``None`` for purely-local commands (``connectb``, ``trace``,
        ``quit``) that don't produce a server response.
        """
        parts = text.strip().split()
        if not parts:
            return None
        cmd, *rest = parts
        cmd = cmd.lower()

        if cmd == "connectb":
            host = rest[0] if len(rest) > 0 else "127.0.0.1"
            port = int(rest[1]) if len(rest) > 1 else 8770
            await self.connectb(host, port)
            return None

        if cmd == "trace":
            if rest and rest[0].lower() == "off":
                self.trace = False
            else:
                self.trace = True
            print(f"trace {'on' if self.trace else 'off'}")
            return None

        if cmd in ("quit", "exit"):
            raise EOFError

        # Everything else needs a connection.
        if self.transport is None:
            print("not connected (use: connectb [host] [port])")
            return None

        seq = self.seq_alloc.next()

        if cmd == "bye":
            # BYE has no terminal response (docs/03 §1.2: "graceful close")
            # -- send it and disconnect without waiting for a reply.
            line = f"{seq} {Verb.BYE.value}"
            if self.trace:
                print(f"-> {line}", file=sys.stderr)
            await self.transport.send(line)
            await self.disconnect()
            return None

        if cmd == "ping":
            line = f"{seq} {Verb.PING.value}"
        elif cmd == "readdtc":
            mask = rest[0] if rest else "FF"
            line = f"{seq} {Verb.READDTC.value} {mask}"
        elif cmd == "cleardtc":
            line = f"{seq} {Verb.CLEARDTC.value}"
        elif cmd == "session":
            if not rest:
                print("usage: session <hex>")
                return None
            line = f"{seq} {Verb.SESSION.value} {rest[0]}"
        elif cmd in ("sec", "security"):
            if not rest:
                print("usage: sec <level_hex>")
                return None
            line = f"{seq} {Verb.SECURITY.value} {rest[0]}"
        elif cmd == "tp":
            if not rest or rest[0].upper() not in ("ON", "OFF"):
                print("usage: tp on|off")
                return None
            sub = "START" if rest[0].upper() == "ON" else "STOP"
            line = f"{seq} {Verb.TP.value} {sub}"
        elif cmd == "raw":
            try:
                hex_to_bytes(" ".join(rest))
            except ValueError as exc:
                print(f"bad hex: {exc}")
                return None
            line = f"{seq} {Verb.RAW.value} {' '.join(rest)}"
        else:
            print(f"unknown command: {cmd!r}")
            return None

        resp = await self._send_and_wait(line)

        if cmd == "readdtc":
            print(self.render_readdtc(resp))
        else:
            print(self.render(resp))

        return resp


async def run_repl(initial_command: str | None = None) -> None:
    """Run the interactive REPL loop on stdin until ``quit``/EOF.

    Args:
        initial_command: If given, run this command (e.g. ``"connectb
            127.0.0.1 8770"``) before handing control to the interactive
            loop. Used by ``__main__.py`` to implement
            ``--host``/``--port``/``--url`` (docs/05 §7).
    """
    repl = Repl()
    loop = asyncio.get_event_loop()
    print("FlexDiag terminal (proto=1). Type 'connectb' to begin, 'quit' to exit.")
    if initial_command is not None:
        try:
            await repl.run_command(initial_command)
        except TransportError as exc:
            print(f"transport error: {exc}")
    while True:
        try:
            text = await loop.run_in_executor(None, input, "flexdiag> ")
        except EOFError:
            break
        try:
            await repl.run_command(text)
        except EOFError:
            break
        except TransportError as exc:
            print(f"transport error: {exc}")
    await repl.disconnect()


def main(initial_command: str | None = None) -> None:
    logging.basicConfig(level=logging.WARNING)
    try:
        asyncio.run(run_repl(initial_command))
    except KeyboardInterrupt:
        pass
