"""TCP wire-protocol front-end for the Mock ECU (M1 software loopback).

For M1, :class:`MockServer` *is* the "server" the terminal connects to over
plain TCP — it stands in for the entire CAPL transport + core + real ECU
stack (``docs/03`` §5). It speaks the proto=1 line protocol using
:mod:`protocol.wire` exclusively; no framing logic is duplicated here.

One client connection is handled at a time (v1; sufficient for loopback
testing). The server runs its own asyncio event loop on a dedicated
background thread so callers (tests, ``__main__``) can use a simple
synchronous ``start()``/``stop()`` API.
"""

from __future__ import annotations

import asyncio
import logging
import threading

from mock_ecu.uds import Ecu
from protocol.wire import (
    CLIENT_VERBS,
    MAX_LINE,
    Command,
    ProtocolError,
    Verb,
    encode_err,
    encode_nrc,
    encode_ok_sec,
    encode_ok_tp,
    encode_pong,
    encode_ready,
    encode_rsp,
    parse_command,
)

logger = logging.getLogger(__name__)


class MockServer:
    """Asyncio TCP server speaking the proto=1 wire protocol.

    Args:
        host: Bind address (default ``127.0.0.1``, per ``docs/04`` §5 -
            localhost-only by default).
        port: Bind port (default ``9000``).
        tool_label: Value reported in ``READY``'s ``tool=`` field.
        transport_label: Value reported in ``READY``'s ``transport=`` field
            (``"A"`` or ``"B"``; defaults to ``"A"`` since the mock stands in
            for the Option A CAPL TCP transport in M1).
        ecu: The :class:`mock_ecu.uds.Ecu` instance backing UDS requests. A
            fresh one is created if not supplied.
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 9000,
        tool_label: str = "Mock",
        transport_label: str = "A",
        ecu: Ecu | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self.tool_label = tool_label
        self.transport_label = transport_label
        self.ecu = ecu if ecu is not None else Ecu()

        self._loop: asyncio.AbstractEventLoop | None = None
        self._server: asyncio.base_events.Server | None = None
        self._thread: threading.Thread | None = None
        self._ready_evt = threading.Event()
        self._bound_port: int | None = None

    @property
    def bound_port(self) -> int:
        """The actual bound TCP port (useful when ``port=0`` was requested)."""
        if self._bound_port is None:
            raise RuntimeError("server not started")
        return self._bound_port

    # ------------------------------------------------------------------
    # lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the server on a background thread and block until bound."""
        if self._thread is not None:
            raise RuntimeError("server already started")
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self._ready_evt.wait()

    def stop(self) -> None:
        """Stop the server and join its thread. Safe to call multiple times."""
        if self._loop is None or self._thread is None:
            return
        asyncio.run_coroutine_threadsafe(self._shutdown(), self._loop)
        self._thread.join(timeout=5)
        self._thread = None
        self._loop = None

    def _run(self) -> None:
        loop = asyncio.new_event_loop()
        self._loop = loop
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self._start_server())
        self._ready_evt.set()
        try:
            loop.run_forever()
        finally:
            loop.close()

    async def _start_server(self) -> None:
        self._server = await asyncio.start_server(self._handle_client, self.host, self.port)
        sockets = self._server.sockets or []
        self._bound_port = sockets[0].getsockname()[1] if sockets else self.port

    async def _shutdown(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
        loop = asyncio.get_event_loop()
        loop.stop()

    # ------------------------------------------------------------------
    # connection handling
    # ------------------------------------------------------------------

    async def _handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        peer = writer.get_extra_info("peername")
        logger.info("client connected: %s", peer)

        # Unsolicited banner, sent immediately on accept (docs/03 §1.3/§3.2).
        await self._send(writer, encode_ready(0, self.tool_label, self.transport_label))

        try:
            while True:
                try:
                    raw = await reader.readuntil(b"\n")
                except asyncio.IncompleteReadError as exc:
                    if exc.partial:
                        logger.info("client disconnected mid-line: %s", peer)
                    break
                except asyncio.LimitOverrunError:
                    # Line exceeded the stream buffer limit -> too long.
                    await self._send(writer, encode_err(0, 422, "bad_args"))
                    writer.close()
                    return

                if len(raw) > MAX_LINE:
                    await self._send(writer, encode_err(0, 422, "bad_args"))
                    writer.close()
                    return

                line = raw.decode("ascii", errors="replace")
                stripped = line.strip()
                if not stripped:
                    continue

                should_close = await self._dispatch(stripped, writer)
                if should_close:
                    break
        finally:
            logger.info("closing connection: %s", peer)
            writer.close()

    @staticmethod
    async def _send(writer: asyncio.StreamWriter, line: str) -> None:
        writer.write(line.encode("ascii"))
        await writer.drain()

    # ------------------------------------------------------------------
    # dispatch
    # ------------------------------------------------------------------

    async def _dispatch(self, line: str, writer: asyncio.StreamWriter) -> bool:
        """Handle one request line. Returns True if the connection should close."""
        # Recover a seq for error responses up front; fall back to 0 if the
        # seq token itself is unparseable (docs/03 §1.5).
        seq = 0
        tokens = line.split()
        if tokens:
            try:
                parsed = int(tokens[0], 10)
                if parsed >= 0:
                    seq = parsed
            except ValueError:
                pass

        # Distinguish "unknown verb" (ERR 400) from "malformed args/hex"
        # (ERR 422) before calling parse_command, which raises a single
        # ProtocolError for both (docs/04 §1.7: unknown verbs -> ERR 400).
        if len(tokens) >= 2:
            verb_tok = tokens[1].upper()
            try:
                verb_candidate = Verb(verb_tok)
            except ValueError:
                await self._send(writer, encode_err(seq, 400, "unknown_verb"))
                return False
            if verb_candidate not in CLIENT_VERBS:
                await self._send(writer, encode_err(seq, 400, "unknown_verb"))
                return False

        try:
            cmd = parse_command(line)
        except ProtocolError:
            await self._send(writer, encode_err(seq, 422, "bad_args"))
            return False

        verb = Verb(cmd.verb)

        if verb == Verb.HELLO:
            await self._send(writer, encode_ready(cmd.seq, self.tool_label, self.transport_label))
            return False

        if verb == Verb.PING:
            await self._send(writer, encode_pong(cmd.seq))
            return False

        if verb == Verb.BYE:
            return True

        if verb == Verb.SESSION:
            await self._handle_session(cmd, writer)
            return False

        if verb == Verb.READDTC:
            await self._handle_readdtc(cmd, writer)
            return False

        if verb == Verb.CLEARDTC:
            await self._handle_cleardtc(cmd, writer)
            return False

        if verb == Verb.SECURITY:
            await self._handle_security(cmd, writer)
            return False

        if verb == Verb.TP:
            await self._handle_tp(cmd, writer)
            return False

        if verb == Verb.RAW:
            await self._handle_raw(cmd, writer)
            return False

        # parse_command already rejects unknown/non-client verbs as
        # ProtocolError, so this branch is unreachable in practice; kept
        # as a defensive fallback.
        await self._send(writer, encode_err(cmd.seq, 400, "unknown_verb"))
        return False

    # ------------------------------------------------------------------
    # request dispatch + response framing
    # ------------------------------------------------------------------

    async def _respond_uds(self, seq: int, req: bytes, writer: asyncio.StreamWriter) -> None:
        """Dispatch ``req`` to the ECU and send RSP/NRC, honoring injections.

        Implements the "respond pending then final" flow for
        ``inject_next(pending_before=True)``: emits ``NRC <sid> 78`` first,
        then immediately re-dispatches the *same* request to obtain the real
        response and sends that too -- both lines carry ``seq`` (an
        intermediate ``NRC 78`` followed by the terminal response is allowed
        by docs/03 §1.4/§1.5: "a command yields exactly one terminal
        response (plus optional EVT lines at seq 0)"; the 0x78 line is an
        ECU NRC, not a second terminal response for a *different* command).

        Implements transport-drop for ``inject_next(drop=True)``: closes the
        connection without sending any response.
        """
        if self.ecu.consume_drop():
            writer.close()
            return

        if self.ecu.consume_pending_before():
            sid = req[0]
            await self._send(writer, encode_nrc(seq, sid, 0x78))
            # Re-dispatch for the real response (pending_before consumed the
            # flag already, and inject_next NRC was not armed for this op).

        rsp = self.ecu.handle(req)
        await self._send_uds_result(seq, rsp, writer)

    async def _send_uds_result(
        self, seq: int, rsp: bytes | None, writer: asyncio.StreamWriter
    ) -> None:
        if rsp is None:
            # No response expected (e.g. suppress-positive TesterPresent).
            # Not reachable from the v1 verb set (TP is handled separately,
            # never via _respond_uds), but guard defensively.
            return
        if rsp[0] == 0x7F:
            sid = rsp[1] if len(rsp) > 1 else 0
            nrc = rsp[2] if len(rsp) > 2 else 0
            await self._send(writer, encode_nrc(seq, sid, nrc))
        else:
            await self._send(writer, encode_rsp(seq, rsp))

    async def _handle_session(self, cmd: Command, writer: asyncio.StreamWriter) -> None:
        if len(cmd.args) != 1:
            await self._send(writer, encode_err(cmd.seq, 422, "bad_args"))
            return
        try:
            sub = int(cmd.args[0], 16)
            if not (0 <= sub <= 0xFF):
                raise ValueError
        except ValueError:
            await self._send(writer, encode_err(cmd.seq, 422, "bad_args"))
            return
        req = bytes([0x10, sub])
        await self._respond_uds(cmd.seq, req, writer)

    async def _handle_readdtc(self, cmd: Command, writer: asyncio.StreamWriter) -> None:
        if len(cmd.args) > 1:
            await self._send(writer, encode_err(cmd.seq, 422, "bad_args"))
            return
        mask_hex = cmd.args[0] if cmd.args else "FF"
        try:
            mask = int(mask_hex, 16)
            if not (0 <= mask <= 0xFF):
                raise ValueError
        except ValueError:
            await self._send(writer, encode_err(cmd.seq, 422, "bad_args"))
            return
        req = bytes([0x19, 0x02, mask])
        await self._respond_uds(cmd.seq, req, writer)

    async def _handle_cleardtc(self, cmd: Command, writer: asyncio.StreamWriter) -> None:
        if cmd.args:
            await self._send(writer, encode_err(cmd.seq, 422, "bad_args"))
            return
        req = bytes([0x14, 0xFF, 0xFF, 0xFF])
        await self._respond_uds(cmd.seq, req, writer)

    async def _handle_raw(self, cmd: Command, writer: asyncio.StreamWriter) -> None:
        if cmd.data is None or len(cmd.data) == 0:
            await self._send(writer, encode_err(cmd.seq, 422, "bad_args"))
            return
        await self._respond_uds(cmd.seq, cmd.data, writer)

    async def _handle_tp(self, cmd: Command, writer: asyncio.StreamWriter) -> None:
        if len(cmd.args) != 1 or cmd.args[0].upper() not in ("START", "STOP"):
            await self._send(writer, encode_err(cmd.seq, 422, "bad_args"))
            return
        # M1: track state at the protocol layer only; periodic 3E emission
        # is deferred to CAPL (docs/03 §3.1, docs/04 §2.8) -- see module
        # docstring / report.
        await self._send(writer, encode_ok_tp(cmd.seq))

    async def _handle_security(self, cmd: Command, writer: asyncio.StreamWriter) -> None:
        """Orchestrate the seed/key dance on the mock side for ``SECURITY <level>``.

        Per the M1 spec, the mock server (not the client) drives both UDS
        round-trips: ``27 <level>`` (request seed), then -- on a positive
        ``67 <level> <seed...>`` -- computes the key via
        :meth:`Ecu.test_key` and sends ``27 <level+1> <key...>``. A positive
        ``67 <level+1>`` yields ``OK SEC <level>``; an NRC at either step
        yields ``NRC 27 <nrc>``.

        NRC injection (:meth:`Ecu.inject_next`) is honored on the *first*
        request (the seed request) only, matching "single-shot" semantics:
        the injected NRC fires for whichever UDS request is dispatched next,
        which is the seed request here.

        The drop/pending-before injections are also only meaningfully
        observed on the seed request for the same reason; if armed they take
        effect via :meth:`_respond_uds`-equivalent handling below.
        """
        if len(cmd.args) != 1:
            await self._send(writer, encode_err(cmd.seq, 422, "bad_args"))
            return
        try:
            level = int(cmd.args[0], 16)
            if not (0 <= level <= 0xFF):
                raise ValueError
        except ValueError:
            await self._send(writer, encode_err(cmd.seq, 422, "bad_args"))
            return

        # --- Step 1: request seed -----------------------------------
        if self.ecu.consume_drop():
            writer.close()
            return

        seed_req = bytes([0x27, level])
        if self.ecu.consume_pending_before():
            await self._send(writer, encode_nrc(cmd.seq, 0x27, 0x78))

        seed_rsp = self.ecu.handle(seed_req)
        assert seed_rsp is not None  # 0x27 always returns bytes

        if seed_rsp[0] == 0x7F:
            nrc = seed_rsp[2] if len(seed_rsp) > 2 else 0
            await self._send(writer, encode_nrc(cmd.seq, 0x27, nrc))
            return

        # seed_rsp = 67 <level> <seed...>
        seed = seed_rsp[2:]

        # --- Step 2: send key ----------------------------------------
        key = self.ecu.test_key(seed, level)
        key_req = bytes([0x27, level + 1, *key])
        key_rsp = self.ecu.handle(key_req)
        assert key_rsp is not None

        if key_rsp[0] == 0x7F:
            nrc = key_rsp[2] if len(key_rsp) > 2 else 0
            await self._send(writer, encode_nrc(cmd.seq, 0x27, nrc))
            return

        await self._send(writer, encode_ok_sec(cmd.seq, level))
