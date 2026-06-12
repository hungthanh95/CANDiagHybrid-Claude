// UDS Negative Response Code (NRC) name table.
//
// For display only -- mirrors `protocol/nrc.py` (docs/03-TECHNICAL-DETAIL.md
// §6.2). No diagnostic logic; just symbolic names for the UI to render.

/// Maps known NRC byte values to their ISO 14229 symbolic names.
const Map<int, String> nrcNames = <int, String>{
  0x10: 'generalReject',
  0x11: 'serviceNotSupported',
  0x12: 'subFunctionNotSupported',
  0x13: 'incorrectMessageLengthOrInvalidFormat',
  0x22: 'conditionsNotCorrect',
  0x31: 'requestOutOfRange',
  0x33: 'securityAccessDenied',
  0x35: 'invalidKey',
  0x36: 'exceedNumberOfAttempts',
  0x37: 'requiredTimeDelayNotExpired',
  0x78: 'responsePending',
  0x7E: 'subFunctionNotSupportedInActiveSession',
  0x7F: 'serviceNotSupportedInActiveSession',
};

/// Returns the symbolic name for [code], or `unknown_XX` (uppercase hex) if
/// unmapped.
String nrcName(int code) {
  final name = nrcNames[code];
  if (name != null) return name;
  return 'unknown_${code.toRadixString(16).toUpperCase().padLeft(2, '0')}';
}
