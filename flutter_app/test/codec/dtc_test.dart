// Tests for lib/codec/dtc.dart -- DTC decode per docs/03-TECHNICAL-DETAIL.md
// §6.1. Mirrors protocol/dtc.py's test_protocol_dtc.py cases.

import 'package:flexdiag_app/codec/dtc.dart';
import 'package:test/test.dart';

void main() {
  group('decodeDtc', () {
    test('00 12 34 -> P01234 (§1.4 example DTC#1)', () {
      expect(decodeDtc(0x00, 0x12, 0x34), 'P01234');
    });

    test('00 56 78 -> P05678 (§1.4 example DTC#2)', () {
      expect(decodeDtc(0x00, 0x56, 0x78), 'P05678');
    });

    test('letter selection: 01 -> C, 10 -> B, 11 -> U', () {
      // b2 top 2 bits select letter; remaining bits arbitrary (use 0).
      expect(decodeDtc(0x00, 0x00, 0x00), 'P00000');
      expect(decodeDtc(0x40, 0x00, 0x00), 'C00000');
      expect(decodeDtc(0x80, 0x00, 0x00), 'B00000');
      expect(decodeDtc(0xC0, 0x00, 0x00), 'U00000');
    });

    test('d1 digit from bits 5:4 of b2', () {
      // b2 = 0b00_11_0000 -> P, d1=3, rest = (0x30 & 0x3F) << 16 = 0x300000
      // -> "3300000" matches protocol/dtc.py's decode_dtc(0x30, 0, 0).
      expect(decodeDtc(0x30, 0x00, 0x00), 'P3300000');
    });

    test('22-bit "rest" rendered as >=4 uppercase hex digits, zero-padded', () {
      // b2 low 6 bits all set, b1/b0 = 0xFF -> rest = 0x3FFFFF -> 6 hex
      // digits (no truncation; %04X is a minimum width). Matches
      // protocol/dtc.py's decode_dtc(0x3F, 0xFF, 0xFF) == "P33FFFFF".
      expect(decodeDtc(0x3F, 0xFF, 0xFF), 'P33FFFFF');
    });
  });

  group('parseReadDtcPayload', () {
    test('parses §1.4 example: 59 02 FF 00 12 34 2F 00 56 78 08', () {
      final payload = <int>[
        0x59, 0x02, 0xFF, //
        0x00, 0x12, 0x34, 0x2F, //
        0x00, 0x56, 0x78, 0x08,
      ];
      final result = parseReadDtcPayload(payload);
      expect(result.availabilityMask, 0xFF);
      expect(result.dtcs, hasLength(2));
      expect(result.dtcs[0].code, 'P01234');
      expect(result.dtcs[0].status, 0x2F);
      expect(result.dtcs[1].code, 'P05678');
      expect(result.dtcs[1].status, 0x08);
    });

    test('empty DTC list (no records after availability mask)', () {
      final result = parseReadDtcPayload(<int>[0x59, 0x02, 0xFF]);
      expect(result.availabilityMask, 0xFF);
      expect(result.dtcs, isEmpty);
    });

    test('throws on too-short payload', () {
      expect(
        () => parseReadDtcPayload(<int>[0x59, 0x02]),
        throwsFormatException,
      );
    });

    test('throws on wrong SID/sub-function', () {
      expect(
        () => parseReadDtcPayload(<int>[0x59, 0x01, 0xFF]),
        throwsFormatException,
      );
      expect(
        () => parseReadDtcPayload(<int>[0x50, 0x02, 0xFF]),
        throwsFormatException,
      );
    });

    test('throws on truncated trailing record', () {
      expect(
        () => parseReadDtcPayload(<int>[0x59, 0x02, 0xFF, 0x00, 0x12, 0x34]),
        throwsFormatException,
      );
    });
  });
}
