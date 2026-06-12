"""Unit tests for :mod:`protocol.nrc` (NRC name table)."""

from __future__ import annotations

from protocol.nrc import nrc_name


def test_nrc_name_invalid_key():
    assert nrc_name(0x35) == "invalidKey"


def test_nrc_name_response_pending():
    assert nrc_name(0x78) == "responsePending"


def test_nrc_name_security_access_denied():
    assert nrc_name(0x33) == "securityAccessDenied"


def test_nrc_name_unknown_returns_unknown_xx():
    assert nrc_name(0xAA) == "unknown_AA"
