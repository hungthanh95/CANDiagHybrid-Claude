"""FlexDiag Option B bridge core: COM/System-Variable <-> WebSocket.

See ``docs/03-TECHNICAL-DETAIL.md`` §4 for the architecture.

Two ``*Com`` backends share the same public surface (``cmd_q``, ``evt_q``,
``.tool``, ``.start()``, ``.stop()``):

- :class:`VectorCom` -- the real COM-backed implementation. Talks to
  CANoe/CANalyzer on a dedicated STA thread (``pythoncom.CoInitialize`` once,
  ``PumpWaitingMessages`` in the loop). ``pythoncom``/``win32com.client`` are
  imported lazily inside ``_run`` so this module imports cleanly on
  non-Windows machines without ``pywin32`` installed.
- :class:`FakeVectorCom` -- a mock-first test double that runs
  ``mock_ecu.uds.Ecu`` in a background thread, simulating what
  ``flexdiag_sysvar.can`` + ``flexdiag_core.can`` would do in response to the
  same ``(seq, kind, arg, data)`` commands.

The WebSocket-facing :func:`handle`/:func:`serve` functions are transport-
agnostic over which ``*Com`` backend is in use (CLAUDE.md rule 4).

The bridge never interprets diagnostic UDS bytes beyond the non-UDS ``OK
TP``/``OK SEC <level>`` formatting in :func:`encode_response` (CLAUDE.md
rule 5 / docs/03 §4.2's note) -- it only moves ``Diag::*`` System Variable
values to/from the wire protocol (``protocol.wire``).
"""

from __future__ import annotations

import asyncio
import logging
import queue
import threading

from mock_ecu.uds import Ecu
from protocol.wire import (
    CLIENT_VERBS,
    MAX_LINE,
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

# ReqKind / RspKind enum (docs/03 §2).
KIND_RAW = 0
KIND_READDTC = 1
KIND_CLEARDTC = 2
KIND_SECURITY = 3
KIND_SESSION = 4
KIND_TP_START = 5
KIND_TP_STOP = 6

# RspStatus enum (docs/03 §2 / §3.1).
STATUS_POSITIVE = 0
STATUS_NEGATIVE = 1
STATUS_OK = 2
STATUS_ERR_KEYGEN = 3
STATUS_ERR_TIMEOUT = 4


class VectorCom:
    """Real COM-backed Option B transport, talking to CANoe/CANalyzer.

    Runs entirely on one dedicated STA thread per docs/03 §4.1: the async
    (WebSocket) side never touches COM/sysvars directly, only via
    ``cmd_q``/``evt_q``.

    Args:
        prefer: ``"auto"`` (try CANoe then CANalyzer), ``"CANoe"``, or
            ``"CANalyzer"``.
        poll_interval: seconds to sleep between ``PumpWaitingMessages``
            polls of ``Diag::RspTrigger`` (default 5 ms).
    """

    def __init__(self, prefer: str = "auto", poll_interval: float = 0.005) -> None:
        self.prefer = prefer
        self.poll_interval = poll_interval
        self.cmd_q: queue.Queue[tuple[int, int, int, bytes | None]] = queue.Queue()
        self.evt_q: queue.Queue[tuple[int, int, int, bytes]] = queue.Queue()
        self.tool: str = ""
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        """Start the dedicated STA/COM thread."""
        self._thread.start()

    def stop(self) -> None:
        """Signal the COM thread to stop and join it."""
        self._stop.set()
        self._thread.join(timeout=5)

    # ------------------------------------------------------------------
    # STA thread body -- lazy COM imports so this module is importable on
    # platforms without pywin32 (Linux dev/test environments).
    # ------------------------------------------------------------------

    def _connect(self, win32com_client: object, prefer: str) -> tuple[object, str]:
        prog_ids = (
            ["CANoe.Application", "CANalyzer.Application"]
            if prefer == "auto"
            else [f"{prefer}.Application"]
        )
        last_exc: Exception | None = None
        for prog_id in prog_ids:
            try:
                app = win32com_client.Dispatch(prog_id)  # type: ignore[attr-defined]
                return app, prog_id.split(".")[0]
            except Exception as exc:  # noqa: BLE001 - try the next ProgID
                last_exc = exc
                continue
        raise RuntimeError(f"No CANoe/CANalyzer COM server available: {last_exc}")

    def _run(self, prefer: str | None = None) -> None:
        import pythoncom
        import win32com.client as win32com_client

        if prefer is None:
            prefer = self.prefer

        pythoncom.CoInitialize()
        try:
            app, tool = self._connect(win32com_client, prefer)
            self.tool = tool

            sysns = app.System.Namespaces.Item("Diag")  # type: ignore[attr-defined]

            def sv(name: str) -> object:
                return sysns.Variables.Item(name)

            last_rsp = int(sv("RspTrigger").Value)  # type: ignore[attr-defined]

            while not self._stop.is_set():
                pythoncom.PumpWaitingMessages()

                # 1) push any pending client command into sysvars.
                try:
                    seq, kind, arg, data = self.cmd_q.get_nowait()
                    if data is not None:
                        sv("ReqData").Value = tuple(data)  # type: ignore[attr-defined]
                    sv("ReqSeq").Value = seq  # type: ignore[attr-defined]
                    sv("ReqKind").Value = kind  # type: ignore[attr-defined]
                    sv("ReqArg").Value = arg  # type: ignore[attr-defined]
                    sv("ReqTrigger").Value = int(sv("ReqTrigger").Value) + 1  # type: ignore[attr-defined]
                except queue.Empty:
                    pass

                # 2) detect a new response.
                cur = int(sv("RspTrigger").Value)  # type: ignore[attr-defined]
                if cur != last_rsp:
                    last_rsp = cur
                    self.evt_q.put(
                        (
                            int(sv("RspSeq").Value),  # type: ignore[attr-defined]
                            int(sv("RspStatus").Value),  # type: ignore[attr-defined]
                            int(sv("RspKind").Value),  # type: ignore[attr-defined]
                            bytes(sv("RspData").Value),  # type: ignore[attr-defined]
                        )
                    )

                self._stop.wait(self.poll_interval)
        finally:
            pythoncom.CoUninitialize()


class FakeVectorCom:
    """Mock-first test double for :class:`VectorCom`.

    Runs a background thread that simulates ``flexdiag_sysvar.can`` +
    ``flexdiag_core.can`` driving :class:`mock_ecu.uds.Ecu`, so the bridge's
    WebSocket-facing logic can be exercised end-to-end without COM/pywin32
    (CLAUDE.md rule 1: mock-first).

    Same public surface as :class:`VectorCom`: ``cmd_q``, ``evt_q``,
    ``.tool`` (``"Mock"``), ``.start()``, ``.stop()``. Additionally exposes
    ``.ecu`` (the :class:`Ecu` instance) so tests can call
    :meth:`Ecu.inject_next`.
    """

    tool = "Mock"

    def __init__(self, ecu: Ecu | None = None) -> None:
        self.ecu = ecu if ecu is not None else Ecu()
        self.cmd_q: queue.Queue[tuple[int, int, int, bytes | None]] = queue.Queue()
        self.evt_q: queue.Queue[tuple[int, int, int, bytes]] = queue.Queue()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        # Unblock cmd_q.get() if the thread is waiting on it.
        self.cmd_q.put((0, -1, 0, None))
        self._thread.join(timeout=5)

    def _run(self) -> None:
        while not self._stop.is_set():
            seq, kind, arg, data = self.cmd_q.get()
            if self._stop.is_set():
                return
            try:
                self._dispatch(seq, kind, arg, data)
            except Exception:  # noqa: BLE001 - never crash the COM thread
                logger.exception("FakeVectorCom: error handling seq=%d kind=%d", seq, kind)

    def _dispatch(self, seq: int, kind: int, arg: int, data: bytes | None) -> None:
        if kind == KIND_RAW:
            assert data is not None
            self._respond_uds(seq, kind, data)
            return

        if kind == KIND_READDTC:
            self._respond_uds(seq, kind, bytes([0x19, 0x02, arg & 0xFF]))
            return

        if kind == KIND_CLEARDTC:
            self._respond_uds(seq, kind, bytes([0x14, 0xFF, 0xFF, 0xFF]))
            return

        if kind == KIND_SESSION:
            self._respond_uds(seq, kind, bytes([0x10, arg & 0xFF]))
            return

        if kind == KIND_SECURITY:
            self._do_security(seq, arg & 0xFF)
            return

        if kind in (KIND_TP_START, KIND_TP_STOP):
            self.evt_q.put((seq, STATUS_OK, kind, b""))
            return

        logger.warning("FakeVectorCom: unknown ReqKind %d (seq=%d)", kind, seq)

    # ------------------------------------------------------------------
    # UDS dispatch helpers
    # ------------------------------------------------------------------

    def _respond_uds(self, seq: int, kind: int, req: bytes) -> None:
        """Dispatch ``req`` to :attr:`ecu`, honoring NRC-injection flags.

        Implements the "pending then final" and "drop" handling described
        in docs/03 §1.4/§1.5.
        """
        if self.ecu.consume_drop():
            return  # simulate a hang: no event pushed

        if self.ecu.consume_pending_before():
            sid = req[0]
            self.evt_q.put((seq, STATUS_NEGATIVE, kind, bytes([0x7F, sid, 0x78])))

        rsp = self.ecu.handle(req)
        if rsp is None:
            return
        status = STATUS_NEGATIVE if rsp[0] == 0x7F else STATUS_POSITIVE
        self.evt_q.put((seq, status, kind, rsp))

    def _do_security(self, seq: int, level: int) -> None:
        """Orchestrate the seed/key dance against :attr:`ecu`.

        ``level`` is the odd level requested via ``SECURITY <level>``. On
        full success pushes ``(seq, STATUS_OK, KIND_SECURITY, 67 <evenLevel>)``
        so the bridge derives ``oddLevel = RspData[1] - 1`` (docs/03 §2/§4.2).
        On an NRC at either step pushes
        ``(seq, STATUS_NEGATIVE, KIND_SECURITY, 7F 27 <nrc>)``.
        """
        if self.ecu.consume_drop():
            return

        seed_req = bytes([0x27, level])
        if self.ecu.consume_pending_before():
            self.evt_q.put((seq, STATUS_NEGATIVE, KIND_SECURITY, bytes([0x7F, 0x27, 0x78])))

        seed_rsp = self.ecu.handle(seed_req)
        assert seed_rsp is not None

        if seed_rsp[0] == 0x7F:
            nrc = seed_rsp[2] if len(seed_rsp) > 2 else 0
            self.evt_q.put((seq, STATUS_NEGATIVE, KIND_SECURITY, bytes([0x7F, 0x27, nrc])))
            return

        # seed_rsp = 67 <level> <seed...>
        seed = seed_rsp[2:]
        key = self.ecu.test_key(seed, level)
        key_req = bytes([0x27, level + 1, *key])
        key_rsp = self.ecu.handle(key_req)
        assert key_rsp is not None

        if key_rsp[0] == 0x7F:
            nrc = key_rsp[2] if len(key_rsp) > 2 else 0
            self.evt_q.put((seq, STATUS_NEGATIVE, KIND_SECURITY, bytes([0x7F, 0x27, nrc])))
            return

        # key_rsp = 67 <evenLevel> -- bridge derives oddLevel = data[1] - 1.
        self.evt_q.put((seq, STATUS_OK, KIND_SECURITY, key_rsp))


# ---------------------------------------------------------------------------
# RspStatus -> wire-line mapping (docs/03 §2, §4.2)
# ---------------------------------------------------------------------------


def encode_response(seq: int, status: int, kind: int, data: bytes) -> str:
    """Encode a ``(seq, status, kind, data)`` event tuple as a wire line.

    Implements the ``RspStatus`` -> wire-line mapping from docs/03 §2:

    - ``0`` (positive) -> ``RSP <hex>``
    - ``1`` (negative/NRC) -> ``NRC <sid> <nrc>`` (``data = 7F <sid> <nrc>``)
    - ``2`` (OK, non-UDS): ``kind`` 5/6 -> ``OK TP``; ``kind`` 3 ->
      ``OK SEC <level>`` where ``level = data[1] - 1`` (``data = 67
      <evenLevel>``)
    - ``3`` -> ``ERR 500 keygen_fail``
    - ``4`` -> ``ERR 504 ecu_timeout``
    """
    if status == STATUS_POSITIVE:
        return encode_rsp(seq, data)

    if status == STATUS_NEGATIVE:
        sid = data[1] if len(data) > 1 else 0
        nrc = data[2] if len(data) > 2 else 0
        return encode_nrc(seq, sid, nrc)

    if status == STATUS_OK:
        if kind == KIND_SECURITY:
            even_level = data[1] if len(data) > 1 else 0
            odd_level = (even_level - 1) & 0xFF
            return encode_ok_sec(seq, odd_level)
        return encode_ok_tp(seq)

    if status == STATUS_ERR_KEYGEN:
        return encode_err(seq, 500, "keygen_fail")

    if status == STATUS_ERR_TIMEOUT:
        return encode_err(seq, 504, "ecu_timeout")

    raise ValueError(f"unknown RspStatus: {status!r}")


# ---------------------------------------------------------------------------
# WebSocket front-end (docs/03 §4.1/§4.2)
# ---------------------------------------------------------------------------


async def handle(websocket: object, vec: VectorCom | FakeVectorCom) -> None:
    """Handle one WebSocket client connection.

    Sends an unsolicited ``READY`` banner on connect, drains ``vec.evt_q``
    in the background and forwards events as response lines, and dispatches
    incoming command lines: ``HELLO``/``PING``/``BYE`` are answered directly
    (never reach ``vec.cmd_q``, per docs/03 §2's note on the ``ReqKind``
    enum); everything else is translated to a ``(seq, kind, arg, data)``
    tuple pushed onto ``vec.cmd_q``.
    """
    await websocket.send(encode_ready(0, vec.tool, "B"))  # type: ignore[attr-defined]

    loop = asyncio.get_event_loop()
    pump_task = asyncio.create_task(_pump_events(websocket, vec, loop))

    try:
        async for line in websocket:  # type: ignore[attr-defined]
            should_close = await _dispatch_line(websocket, vec, line)
            if should_close:
                break
    finally:
        pump_task.cancel()


def _get_event_nowait_or_timeout(
    vec: VectorCom | FakeVectorCom, timeout: float
) -> tuple[int, int, int, bytes] | None:
    """``vec.evt_q.get(timeout=timeout)``, returning ``None`` on timeout.

    Used by :func:`_pump_events` so the executor thread periodically returns
    control to the event loop instead of blocking forever on
    ``queue.Queue.get()`` -- an uncancellable blocking call would otherwise
    leak a non-daemon ``ThreadPoolExecutor`` worker thread for the lifetime
    of the process every time a connection closes (``pump_task.cancel()``
    cannot interrupt a blocking ``get()``).
    """
    try:
        return vec.evt_q.get(timeout=timeout)
    except queue.Empty:
        return None


async def _pump_events(
    websocket: object, vec: VectorCom | FakeVectorCom, loop: asyncio.AbstractEventLoop
) -> None:
    while True:
        item = await loop.run_in_executor(None, _get_event_nowait_or_timeout, vec, 0.2)
        if item is None:
            continue  # timed out -- give asyncio a chance to observe cancellation
        seq, status, kind, data = item
        try:
            await websocket.send(encode_response(seq, status, kind, data))  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001 - connection closed etc.
            logger.debug("event send failed (seq=%d), dropping", seq)
            return


async def _dispatch_line(websocket: object, vec: VectorCom | FakeVectorCom, line: str) -> bool:
    """Handle one client -> server line. Returns True if the connection should close.

    Implements the ERR-400-vs-422 dispatch pattern: unknown verbs ->
    ``ERR 400 unknown_verb`` (checked before ``parse_command``); malformed
    args/hex -> ``ERR 422 bad_args``.
    """
    stripped = line.strip()
    if not stripped:
        return False

    tokens = stripped.split()
    seq = 0
    if tokens:
        try:
            parsed = int(tokens[0], 10)
            if parsed >= 0:
                seq = parsed
        except ValueError:
            pass

    if len(tokens) >= 2:
        verb_tok = tokens[1].upper()
        try:
            verb_candidate = Verb(verb_tok)
        except ValueError:
            await websocket.send(encode_err(seq, 400, "unknown_verb"))  # type: ignore[attr-defined]
            return False
        if verb_candidate not in CLIENT_VERBS:
            await websocket.send(encode_err(seq, 400, "unknown_verb"))  # type: ignore[attr-defined]
            return False

    try:
        cmd = parse_command(stripped)
    except ProtocolError:
        await websocket.send(encode_err(seq, 422, "bad_args"))  # type: ignore[attr-defined]
        return False

    verb = Verb(cmd.verb)

    if verb == Verb.HELLO:
        await websocket.send(encode_ready(cmd.seq, vec.tool, "B"))  # type: ignore[attr-defined]
        return False

    if verb == Verb.PING:
        await websocket.send(encode_pong(cmd.seq))  # type: ignore[attr-defined]
        return False

    if verb == Verb.BYE:
        return True

    if verb == Verb.SESSION:
        if len(cmd.args) != 1:
            await websocket.send(encode_err(cmd.seq, 422, "bad_args"))  # type: ignore[attr-defined]
            return False
        try:
            session = int(cmd.args[0], 16)
            if not (0 <= session <= 0xFF):
                raise ValueError
        except ValueError:
            await websocket.send(encode_err(cmd.seq, 422, "bad_args"))  # type: ignore[attr-defined]
            return False
        vec.cmd_q.put((cmd.seq, KIND_SESSION, session, None))
        return False

    if verb == Verb.READDTC:
        if len(cmd.args) > 1:
            await websocket.send(encode_err(cmd.seq, 422, "bad_args"))  # type: ignore[attr-defined]
            return False
        mask_hex = cmd.args[0] if cmd.args else "FF"
        try:
            mask = int(mask_hex, 16)
            if not (0 <= mask <= 0xFF):
                raise ValueError
        except ValueError:
            await websocket.send(encode_err(cmd.seq, 422, "bad_args"))  # type: ignore[attr-defined]
            return False
        vec.cmd_q.put((cmd.seq, KIND_READDTC, mask, None))
        return False

    if verb == Verb.CLEARDTC:
        if cmd.args:
            await websocket.send(encode_err(cmd.seq, 422, "bad_args"))  # type: ignore[attr-defined]
            return False
        vec.cmd_q.put((cmd.seq, KIND_CLEARDTC, 0, None))
        return False

    if verb == Verb.SECURITY:
        if len(cmd.args) != 1:
            await websocket.send(encode_err(cmd.seq, 422, "bad_args"))  # type: ignore[attr-defined]
            return False
        try:
            level = int(cmd.args[0], 16)
            if not (0 <= level <= 0xFF):
                raise ValueError
        except ValueError:
            await websocket.send(encode_err(cmd.seq, 422, "bad_args"))  # type: ignore[attr-defined]
            return False
        vec.cmd_q.put((cmd.seq, KIND_SECURITY, level, None))
        return False

    if verb == Verb.TP:
        if len(cmd.args) != 1 or cmd.args[0].upper() not in ("START", "STOP"):
            await websocket.send(encode_err(cmd.seq, 422, "bad_args"))  # type: ignore[attr-defined]
            return False
        kind = KIND_TP_START if cmd.args[0].upper() == "START" else KIND_TP_STOP
        vec.cmd_q.put((cmd.seq, kind, 0, None))
        return False

    if verb == Verb.RAW:
        if cmd.data is None or len(cmd.data) == 0:
            await websocket.send(encode_err(cmd.seq, 422, "bad_args"))  # type: ignore[attr-defined]
            return False
        vec.cmd_q.put((cmd.seq, KIND_RAW, 0, cmd.data))
        return False

    # parse_command already rejects unknown/non-client verbs; defensive only.
    await websocket.send(encode_err(cmd.seq, 400, "unknown_verb"))  # type: ignore[attr-defined]
    return False


async def serve(host: str, port: int, vec: VectorCom | FakeVectorCom) -> None:
    """Start the WebSocket server and run forever (until cancelled)."""
    import websockets

    async with websockets.serve(lambda ws: handle(ws, vec), host, port, max_size=MAX_LINE + 64):
        logger.info("FlexDiag bridge listening on ws://%s:%d/ (tool=%s)", host, port, vec.tool)
        await asyncio.Future()  # run forever


class BridgeServer:
    """Synchronous test harness around :func:`serve` + :class:`FakeVectorCom`.

    Provides ``start()``/``stop()``/``bound_port``/``.ecu`` so Option-B
    tests can drive the bridge against the Mock ECU (mock-first, CLAUDE.md
    rule 1). Runs the bridge's asyncio WebSocket server on a dedicated
    background thread; ``port=0`` binds an ephemeral port, exposed via
    :attr:`bound_port` once :meth:`start` returns.

    Args:
        host: Bind address (default ``127.0.0.1``).
        port: Bind port (``0`` for an OS-assigned ephemeral port).
        vec: The ``*Com`` backend (defaults to a fresh :class:`FakeVectorCom`).
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 0,
        vec: FakeVectorCom | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self.vec = vec if vec is not None else FakeVectorCom()

        self._loop: asyncio.AbstractEventLoop | None = None
        self._server: object | None = None
        self._thread: threading.Thread | None = None
        self._ready_evt = threading.Event()
        self._bound_port: int | None = None

    @property
    def ecu(self) -> Ecu:
        """The :class:`mock_ecu.uds.Ecu` backing :attr:`vec` (for ``inject_next``)."""
        return self.vec.ecu

    @property
    def bound_port(self) -> int:
        """The actual bound WebSocket port (useful when ``port=0`` was requested)."""
        if self._bound_port is None:
            raise RuntimeError("server not started")
        return self._bound_port

    def start(self) -> None:
        """Start :attr:`vec` and the WebSocket server on a background thread."""
        if self._thread is not None:
            raise RuntimeError("server already started")
        self.vec.start()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self._ready_evt.wait()

    def stop(self) -> None:
        """Stop the server, join its thread, and stop :attr:`vec`. Idempotent."""
        if self._loop is not None and self._thread is not None:
            asyncio.run_coroutine_threadsafe(self._shutdown(), self._loop)
            self._thread.join(timeout=5)
            self._thread = None
            self._loop = None
        self.vec.stop()

    def _run(self) -> None:
        import websockets

        loop = asyncio.new_event_loop()
        self._loop = loop
        asyncio.set_event_loop(loop)

        async def _start() -> None:
            self._server = await websockets.serve(
                lambda ws: handle(ws, self.vec),
                self.host,
                self.port,
                max_size=MAX_LINE + 64,
                # Short close_timeout: test clients may disconnect abruptly
                # (their own event loop torn down between pytest fixtures)
                # rather than completing a clean close handshake. Without
                # this, wait_closed() in _shutdown() can block for the
                # default 10s per connection, making stop()'s
                # thread.join(timeout=5) time out on every test.
                close_timeout=0.1,
            )
            self._bound_port = self._server.sockets[0].getsockname()[1]  # type: ignore[union-attr]

        loop.run_until_complete(_start())
        self._ready_evt.set()
        try:
            loop.run_forever()
        finally:
            loop.close()

    async def _shutdown(self) -> None:
        if self._server is not None:
            self._server.close()  # type: ignore[attr-defined]
            await self._server.wait_closed()  # type: ignore[attr-defined]
        loop = asyncio.get_event_loop()
        loop.stop()
