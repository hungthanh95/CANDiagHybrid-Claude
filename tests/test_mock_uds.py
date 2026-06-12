"""Unit tests for :mod:`mock_ecu.uds` (Ecu.handle pure-byte interface)."""

from __future__ import annotations

from mock_ecu.uds import Ecu

# ---------------------------------------------------------------------------
# 0x10 DiagnosticSessionControl
# ---------------------------------------------------------------------------


def test_session_control_positive_response():
    ecu = Ecu()
    rsp = ecu.handle(bytes([0x10, 0x03]))
    assert rsp is not None
    assert rsp[:2] == bytes([0x50, 0x03])
    assert ecu.session == 0x03


# ---------------------------------------------------------------------------
# 0x3E TesterPresent
# ---------------------------------------------------------------------------


def test_tester_present_positive():
    ecu = Ecu()
    rsp = ecu.handle(bytes([0x3E, 0x00]))
    assert rsp == bytes([0x7E, 0x00])


def test_tester_present_suppress_positive():
    ecu = Ecu()
    rsp = ecu.handle(bytes([0x3E, 0x80]))
    assert rsp is None


# ---------------------------------------------------------------------------
# 0x19 02 ReadDtcInformation
# ---------------------------------------------------------------------------


def test_read_dtc_default_mask_ff():
    ecu = Ecu()
    rsp = ecu.handle(bytes([0x19, 0x02, 0xFF]))
    assert rsp is not None
    assert rsp[:3] == bytes([0x59, 0x02, 0xFF])
    body = rsp[3:]
    assert len(body) == 8  # 2 records * 4 bytes
    rec0 = body[0:4]
    rec1 = body[4:8]
    assert rec0 == bytes([0x00, 0x12, 0x34, 0x2F])
    assert rec1 == bytes([0x00, 0x56, 0x78, 0x08])


def test_read_dtc_mask_0f_both_pass():
    # status 0x2F & 0x0F = 0x0F (truthy) -> passes
    # status 0x08 & 0x0F = 0x08 (truthy) -> passes
    ecu = Ecu()
    rsp = ecu.handle(bytes([0x19, 0x02, 0x0F]))
    assert rsp is not None
    body = rsp[3:]
    assert len(body) == 8
    statuses = {body[i + 3] for i in range(0, len(body), 4)}
    assert statuses == {0x2F, 0x08}


def test_read_dtc_mask_20_only_first_passes():
    # status 0x2F & 0x20 = 0x20 (truthy) -> passes
    # status 0x08 & 0x20 = 0x00 (falsy) -> filtered out
    ecu = Ecu()
    rsp = ecu.handle(bytes([0x19, 0x02, 0x20]))
    assert rsp is not None
    body = rsp[3:]
    assert len(body) == 4
    assert body == bytes([0x00, 0x12, 0x34, 0x2F])


def test_read_dtc_mask_40_neither_passes():
    # status 0x2F & 0x40 = 0x00, status 0x08 & 0x40 = 0x00 -> both filtered
    ecu = Ecu()
    rsp = ecu.handle(bytes([0x19, 0x02, 0x40]))
    assert rsp is not None
    body = rsp[3:]
    assert body == b""
    assert rsp[:3] == bytes([0x59, 0x02, 0xFF])


# ---------------------------------------------------------------------------
# 0x14 ClearDiagnosticInformation
# ---------------------------------------------------------------------------


def test_clear_dtc():
    ecu = Ecu()
    rsp = ecu.handle(bytes([0x14, 0xFF, 0xFF, 0xFF]))
    assert rsp == bytes([0x54])


# ---------------------------------------------------------------------------
# 0x27 SecurityAccess: seed/key flow
# ---------------------------------------------------------------------------


def test_security_seed_request():
    ecu = Ecu()
    rsp = ecu.handle(bytes([0x27, 0x01]))
    assert rsp == bytes([0x67, 0x01, 0x11, 0x22, 0x33, 0x44])
    assert ecu.pending_seed_level == 0x01


def test_security_wrong_key_then_correct_key():
    ecu = Ecu()

    # Step 1: request seed.
    seed_rsp = ecu.handle(bytes([0x27, 0x01]))
    assert seed_rsp == bytes([0x67, 0x01, 0x11, 0x22, 0x33, 0x44])

    # Step 2: send wrong key -> invalidKey.
    wrong_key = bytes([0x00, 0x00, 0x00, 0x00])
    bad_rsp = ecu.handle(bytes([0x27, 0x02, *wrong_key]))
    assert bad_rsp == bytes([0x7F, 0x27, 0x35])
    assert ecu.unlocked is False
    # KNOWN DEFECT (filed for flexdiag-reviewer/flexdiag-developer, 0x27 path
    # is protected per CLAUDE.md §3 rule 3 -- not fixed here): the M1 spec
    # (docs/03 §5 sketch + task spec section D/E) describes invalidKey as
    # "reset pending", i.e. ecu.pending_seed_level should become None so a
    # stale seed cannot be retried with a different key. The current
    # mock_ecu.uds.Ecu.handle() does NOT reset pending_seed_level on the
    # 0x35 branch -- it stays at the previously-requested odd level. This
    # test pins the *current* (buggy) behaviour so a future fix is a
    # deliberate, reviewed change rather than a silent regression.
    assert ecu.pending_seed_level == 0x01

    # Step 3: request seed again (always overwrites pending_seed_level
    # regardless of its prior value, so this step is unaffected by the
    # defect above).
    seed_rsp2 = ecu.handle(bytes([0x27, 0x01]))
    assert seed_rsp2 == bytes([0x67, 0x01, 0x11, 0x22, 0x33, 0x44])
    assert ecu.pending_seed_level == 0x01

    # Step 4: send correct key (seed ^ 0x5A) -> unlock.
    seed_bytes = seed_rsp2[2:]
    correct_key = bytes(b ^ 0x5A for b in seed_bytes)
    ok_rsp = ecu.handle(bytes([0x27, 0x02, *correct_key]))
    assert ok_rsp == bytes([0x67, 0x02])
    assert ecu.unlocked is True
    assert ecu.pending_seed_level is None


# ---------------------------------------------------------------------------
# Unknown SID
# ---------------------------------------------------------------------------


def test_unknown_sid_returns_service_not_supported():
    ecu = Ecu()
    rsp = ecu.handle(bytes([0x99]))
    assert rsp == bytes([0x7F, 0x99, 0x11])


# ---------------------------------------------------------------------------
# NRC injection
# ---------------------------------------------------------------------------


def test_inject_next_nrc_consumed_once():
    ecu = Ecu()
    ecu.inject_next(nrc=0x33)

    rsp1 = ecu.handle(bytes([0x19, 0x02, 0xFF]))
    assert rsp1 == bytes([0x7F, 0x19, 0x33])

    # Injection is consumed; the next call is back to normal.
    rsp2 = ecu.handle(bytes([0x19, 0x02, 0xFF]))
    assert rsp2[:3] == bytes([0x59, 0x02, 0xFF])
