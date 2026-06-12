// DTC decoding from `59 02` (ReadDtcInformation) response payloads.
//
// Mirrors `protocol/dtc.py` (docs/03-TECHNICAL-DETAIL.md §6.1) -- keep both
// in sync if the decode algorithm ever changes (protocol/sysvar freeze rules
// apply if that happens, see docs/04 §1.2).

const List<String> _letters = <String>['P', 'C', 'B', 'U'];

/// A single decoded DTC record.
///
/// [code] is the human-readable DTC string (e.g. `"P01234"`), [status] is
/// the raw DTCStatusMask byte, and [b2]/[b1]/[b0] are the original 3 DTC
/// bytes as received on the wire.
class Dtc {
  const Dtc({
    required this.code,
    required this.status,
    required this.b2,
    required this.b1,
    required this.b0,
  });

  final String code;
  final int status;
  final int b2;
  final int b1;
  final int b0;
}

/// Result of [parseReadDtcPayload]: the availability mask echoed by the ECU
/// plus the decoded DTC records.
class ReadDtcResult {
  const ReadDtcResult({required this.availabilityMask, required this.dtcs});

  final int availabilityMask;
  final List<Dtc> dtcs;
}

/// Decode 3 DTC bytes to a human-readable code string.
///
/// Per docs/03 §6.1:
///
/// - Top 2 bits of [b2] select the letter: `00->P`, `01->C`, `10->B`,
///   `11->U`.
/// - Next 2 bits of [b2] (bits 5:4) are the first digit, `0`-`3`.
/// - The remaining 22 bits (low 6 bits of [b2], all of [b1], all of [b0])
///   are rendered as hex digits, zero-padded to a minimum of 4 digits
///   (mirroring Python's `f"{rest:04X}"` -- `04` is a *minimum* width, not
///   a truncation, so values needing more than 4 digits render wider).
///
/// Implemented faithfully to the §6.1 sketch and `protocol/dtc.py`'s
/// `decode_dtc` (which this mirrors -- see docs/04 §1 "one codec per
/// language must stay in sync"): the result is
/// `letter + d1 + (>=4)-hex-digit(rest)`, e.g. `b2=0x00, b1=0x12, b0=0x34`
/// -> `"P01234"`. This is a 6-character code (not the conventional
/// 5-character `P0123` form); do not "correct" it without a
/// protocol/codec review.
String decodeDtc(int b2, int b1, int b0) {
  final letter = _letters[(b2 >> 6) & 0x03];
  final d1 = (b2 >> 4) & 0x03;
  final rest = ((b2 & 0x3F) << 16) | (b1 << 8) | b0;
  final restHex = rest.toRadixString(16).toUpperCase().padLeft(4, '0');
  return '$letter$d1$restHex';
}

/// Parse a full `59 02 <availabilityMask> [<b2><b1><b0><status>]...` payload.
///
/// Throws [FormatException] if the payload is too short, has the wrong
/// SID/sub-function, or has a truncated trailing record.
ReadDtcResult parseReadDtcPayload(List<int> payload) {
  if (payload.length < 3) {
    throw FormatException('READDTC payload too short: $payload');
  }
  if (payload[0] != 0x59 || payload[1] != 0x02) {
    final sid = payload[0].toRadixString(16).toUpperCase().padLeft(2, '0');
    final sub = payload[1].toRadixString(16).toUpperCase().padLeft(2, '0');
    throw FormatException('not a 59 02 payload: $sid $sub');
  }

  final availabilityMask = payload[2];
  final body = payload.sublist(3);
  if (body.length % 4 != 0) {
    throw FormatException(
      'truncated DTC record(s): ${body.length} trailing bytes',
    );
  }

  final dtcs = <Dtc>[];
  for (var i = 0; i < body.length; i += 4) {
    final b2 = body[i];
    final b1 = body[i + 1];
    final b0 = body[i + 2];
    final status = body[i + 3];
    dtcs.add(
      Dtc(code: decodeDtc(b2, b1, b0), status: status, b2: b2, b1: b1, b0: b0),
    );
  }

  return ReadDtcResult(availabilityMask: availabilityMask, dtcs: dtcs);
}
