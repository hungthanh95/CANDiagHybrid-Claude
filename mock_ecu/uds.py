"""Pure UDS responder logic for the Mock ECU.

No I/O here — :class:`Ecu` is a pure state machine over raw UDS request/
response bytes (``docs/03-TECHNICAL-DETAIL.md`` §5 sketch). The Option B
wire framing lives in :mod:`bridge.flexdiag_bridge` (``FakeVectorCom``,
``bridge --fake``).

Implements, per the §5 sketch and the M1 task spec:

- ``0x10`` DiagnosticSessionControl.
- ``0x3E`` TesterPresent (suppress-positive aware).
- ``0x19 02`` ReadDtcInformation (reportDtcByStatusMask).
- ``0x14`` ClearDiagnosticInformation (always full clear in v1).
- ``0x27`` SecurityAccess (seed/key, test algorithm).
- Anything else -> ``7F <sid> 0x11`` (serviceNotSupported).

NRC injection (FR-23) is exposed via :meth:`Ecu.inject_next`.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Ecu:
    """A minimal stateful UDS ECU used for offline/loopback testing.

    Attributes:
        session: Current diagnostic session id (defaults to ``0x01``,
            default session).
        unlocked: Whether security access has been granted.
        pending_seed_level: The odd security level for which a seed was
            most recently issued (awaiting the matching ``sendKey``), or
            ``None`` if no seed is outstanding.
        dtcs: Table of ``(3-byte DTC, status)`` pairs returned by
            ``0x19 02``.
        SEED: Fixed seed bytes returned by ``requestSeed``.

    The seed/key algorithm (:meth:`test_key`) is the **v1 test algorithm**:
    ``key[i] = seed[i] ^ 0x5A``. This is documented here and must match the
    test seed-key DLL used by CAPL (``docs/04`` §3.4) for the offline
    security flow to be meaningful. It is NOT a real algorithm and must
    never be used outside test/mock contexts.
    """

    session: int = 0x01
    unlocked: bool = False
    pending_seed_level: int | None = None
    dtcs: list[tuple[int, int]] = field(
        default_factory=lambda: [(0x001234, 0x2F), (0x005678, 0x08)]
    )
    SEED: bytes = bytes([0x11, 0x22, 0x33, 0x44])

    # --- NRC injection state (FR-23, single-shot) -------------------------
    _inject_nrc: int | None = field(default=None, repr=False, compare=False)
    _inject_pending_before: bool = field(default=False, repr=False, compare=False)
    _inject_drop: bool = field(default=False, repr=False, compare=False)

    @staticmethod
    def test_key(seed: bytes, level: int) -> bytes:  # noqa: ARG004 - level kept for API symmetry
        """Compute the security-access key from ``seed``.

        v1 test algorithm: ``key[i] = seed[i] ^ 0x5A`` for each byte.
        ``level`` is accepted for API symmetry with a real seed-key DLL
        signature (some algorithms vary the transform by level) but is
        unused by the test algorithm.
        """
        return bytes(b ^ 0x5A for b in seed)

    def inject_next(
        self,
        nrc: int | None = None,
        pending_before: bool = False,
        drop: bool = False,
    ) -> None:
        """Arm a single-shot test injection for the *next* request (FR-23).

        - ``nrc``: the next call to :meth:`handle` returns
          ``7F <sid> nrc`` instead of the real response (where ``sid`` is
          the SID of that next request).
        - ``pending_before``: the framing layer (``bridge.flexdiag_bridge``)
          should emit ``7F <sid> 0x78`` (responsePending) once for the next
          request, then immediately re-dispatch to get the *real* response
          and send that as the terminal response. :meth:`handle` itself
          does not implement the 0x78 framing -- it only exposes the armed
          flag via :attr:`pending_before_armed` / :meth:`consume_pending_before`
          so the bridge can implement the two-message sequence.
        - ``drop``: the framing layer should close the connection without
          sending any response for the next request. :meth:`handle` exposes
          this via :attr:`drop_armed` / :meth:`consume_drop`.

        These three modes are mutually exclusive per call but the dataclass
        does not enforce that beyond "last write wins" -- callers (tests)
        should arm one mode at a time.
        """
        self._inject_nrc = nrc
        self._inject_pending_before = pending_before
        self._inject_drop = drop

    @property
    def pending_before_armed(self) -> bool:
        """Whether a ``0x78``-then-final injection is armed."""
        return self._inject_pending_before

    @property
    def drop_armed(self) -> bool:
        """Whether a transport-drop injection is armed."""
        return self._inject_drop

    def consume_pending_before(self) -> bool:
        """Consume (clear) the pending-before injection; return prior state."""
        armed = self._inject_pending_before
        self._inject_pending_before = False
        return armed

    def consume_drop(self) -> bool:
        """Consume (clear) the drop injection; return prior state."""
        armed = self._inject_drop
        self._inject_drop = False
        return armed

    def _consume_nrc(self) -> int | None:
        nrc = self._inject_nrc
        self._inject_nrc = None
        return nrc

    def handle(self, req: bytes) -> bytes | None:
        """Process one raw UDS request and return the raw response bytes.

        Returns ``None`` for requests that elicit no response at all (e.g.
        TesterPresent with the suppress-positive-response bit set).

        If a one-shot NRC injection is armed (:meth:`inject_next` with
        ``nrc=...``), this call consumes it and returns
        ``7F <sid> <nrc>`` instead of the normal response (the real
        response is *not* computed, so state machines like security/session
        are not advanced by an injected-NRC call).
        """
        if not req:
            raise ValueError("empty UDS request")

        sid = req[0]

        injected = self._consume_nrc()
        if injected is not None:
            return bytes([0x7F, sid, injected])

        if sid == 0x10:  # DiagnosticSessionControl
            if len(req) < 2:
                return bytes([0x7F, sid, 0x13])  # incorrectMessageLength
            self.session = req[1]
            return bytes([0x50, req[1], 0x00, 0x32, 0x01, 0xF4])

        if sid == 0x3E:  # TesterPresent
            if len(req) > 1 and (req[1] & 0x80):
                return None  # suppress-positive
            return bytes([0x7E, 0x00])

        if sid == 0x19:  # ReadDtcInformation
            if len(req) < 3 or req[1] != 0x02:
                return bytes([0x7F, sid, 0x12])  # subFunctionNotSupported
            mask = req[2]
            out = bytearray([0x59, 0x02, 0xFF])
            for dtc, status in self.dtcs:
                if status & mask:
                    out += bytes([(dtc >> 16) & 0xFF, (dtc >> 8) & 0xFF, dtc & 0xFF, status])
            return bytes(out)

        if sid == 0x14:  # ClearDiagnosticInformation (v1: always full clear)
            return bytes([0x54])

        if sid == 0x27:  # SecurityAccess
            if len(req) < 2:
                return bytes([0x7F, sid, 0x13])
            level = req[1]
            if level % 2 == 1:  # odd level => requestSeed
                self.pending_seed_level = level
                return bytes([0x67, level]) + self.SEED
            # even level => sendKey
            if self.pending_seed_level is None:
                return bytes([0x7F, sid, 0x24])  # requestSequenceError
            expected = self.test_key(self.SEED, self.pending_seed_level)
            key = bytes(req[2:])
            if key == expected:
                self.unlocked = True
                self.pending_seed_level = None
                return bytes([0x67, level])
            return bytes([0x7F, sid, 0x35])  # invalidKey

        return bytes([0x7F, sid, 0x11])  # serviceNotSupported
