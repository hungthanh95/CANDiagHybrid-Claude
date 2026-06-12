"""UDS Negative Response Code (NRC) name table.

For display only — mirrors ``flutter_app``'s NRC table (docs/03 §6.2). No
diagnostic logic; just symbolic names for the client/terminal to render.
"""

from __future__ import annotations

NRC_NAMES: dict[int, str] = {
    0x10: "generalReject",
    0x11: "serviceNotSupported",
    0x12: "subFunctionNotSupported",
    0x13: "incorrectMessageLengthOrInvalidFormat",
    0x22: "conditionsNotCorrect",
    0x31: "requestOutOfRange",
    0x33: "securityAccessDenied",
    0x35: "invalidKey",
    0x36: "exceedNumberOfAttempts",
    0x37: "requiredTimeDelayNotExpired",
    0x78: "responsePending",
    0x7E: "subFunctionNotSupportedInActiveSession",
    0x7F: "serviceNotSupportedInActiveSession",
}


def nrc_name(code: int) -> str:
    """Return the symbolic name for ``code``, or ``unknown_XX`` if unmapped."""
    return NRC_NAMES.get(code, f"unknown_{code:02X}")
