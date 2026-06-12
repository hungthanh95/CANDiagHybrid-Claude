// Tests for lib/protocol/codec.dart -- proto=1 wire codec
// (docs/03-TECHNICAL-DETAIL.md §1). Mirrors protocol/wire.py's
// test_protocol_wire.py cases for the verbs the Flutter client uses.

import 'package:flexdiag_app/protocol/codec.dart';
import 'package:test/test.dart';

void main() {
  group('bytesToHex / hexToBytes', () {
    test('bytesToHex basic', () {
      expect(bytesToHex(<int>[]), '');
      expect(bytesToHex(<int>[0x00]), '00');
      expect(bytesToHex(<int>[0x22, 0xF1, 0x90]), '22 F1 90');
      expect(bytesToHex(<int>[0xFF, 0x0A]), 'FF 0A');
    });

    test('hexToBytes round trip', () {
      expect(hexToBytes(bytesToHex(<int>[])), <int>[]);
      expect(hexToBytes(bytesToHex(<int>[0x22, 0xF1, 0x90])),
          <int>[0x22, 0xF1, 0x90]);
    });

    test('hexToBytes empty and whitespace', () {
      expect(hexToBytes(''), <int>[]);
      expect(hexToBytes('   '), <int>[]);
    });

    test('hexToBytes lowercase accepted', () {
      expect(hexToBytes('22 f1 90'), <int>[0x22, 0xF1, 0x90]);
      expect(hexToBytes('aB'), <int>[0xAB]);
    });

    test('hexToBytes odd-length token throws', () {
      expect(() => hexToBytes('1'), throwsFormatException);
      expect(() => hexToBytes('22 F'), throwsFormatException);
    });

    test('hexToBytes non-hex chars throws', () {
      expect(() => hexToBytes('GG'), throwsFormatException);
      expect(() => hexToBytes('22 ZZ'), throwsFormatException);
    });

    test('hexToBytes 0x prefix throws', () {
      expect(() => hexToBytes('0x22'), throwsFormatException);
    });
  });

  group('encode commands', () {
    test('HELLO', () {
      expect(encodeHello(1), '1 HELLO proto=1');
    });

    test('SESSION', () {
      expect(encodeSession(16, 0x03), '16 SESSION 03');
    });

    test('READDTC with default mask', () {
      expect(encodeReadDtc(12), '12 READDTC FF');
    });

    test('READDTC with explicit mask', () {
      expect(encodeReadDtc(12, mask: 0x2F), '12 READDTC 2F');
    });

    test('CLEARDTC', () {
      expect(encodeClearDtc(7), '7 CLEARDTC');
    });

    test('SECURITY', () {
      expect(encodeSecurity(13, 0x01), '13 SECURITY 01');
    });

    test('TP START / STOP', () {
      expect(encodeTpStart(15), '15 TP START');
      expect(encodeTpStop(15), '15 TP STOP');
    });

    test('RAW', () {
      expect(encodeRaw(14, <int>[0x22, 0xF1, 0x90]), '14 RAW 22 F1 90');
    });

    test('RAW with empty payload', () {
      expect(encodeRaw(14, <int>[]), '14 RAW');
    });

    test('PING', () {
      expect(encodePing(2), '2 PING');
    });

    test('BYE', () {
      expect(encodeBye(3), '3 BYE');
    });
  });

  group('parseResponse', () {
    test('READY unsolicited banner', () {
      final resp = parseResponse('0 READY proto=1 tool=CANoe transport=B');
      expect(resp.seq, 0);
      expect(resp.verb, Verb.ready);
      expect(resp.proto, 1);
      expect(resp.tool, 'CANoe');
      expect(resp.transport, 'B');
    });

    test('READY echoed to HELLO', () {
      final resp = parseResponse('1 READY proto=1 tool=CANalyzer transport=B');
      expect(resp.seq, 1);
      expect(resp.verb, Verb.ready);
      expect(resp.tool, 'CANalyzer');
    });

    test('RSP', () {
      final resp = parseResponse('12 RSP 59 02 FF 00 12 34 2F 00 56 78 08');
      expect(resp.seq, 12);
      expect(resp.verb, Verb.rsp);
      expect(resp.data, <int>[
        0x59,
        0x02,
        0xFF,
        0x00,
        0x12,
        0x34,
        0x2F,
        0x00,
        0x56,
        0x78,
        0x08
      ]);
    });

    test('RSP for SESSION (uses RSP, never OK)', () {
      final resp = parseResponse('16 RSP 50 03 00 32 01 F4');
      expect(resp.verb, Verb.rsp);
      expect(resp.data, <int>[0x50, 0x03, 0x00, 0x32, 0x01, 0xF4]);
    });

    test('NRC', () {
      final resp = parseResponse('13 NRC 27 35');
      expect(resp.seq, 13);
      expect(resp.verb, Verb.nrc);
      expect(resp.sid, 0x27);
      expect(resp.nrc, 0x35);
    });

    test('OK TP', () {
      final resp = parseResponse('15 OK TP');
      expect(resp.seq, 15);
      expect(resp.verb, Verb.ok);
      expect(resp.okKind, 'TP');
    });

    test('OK SEC <level> -- level is the odd level requested', () {
      final resp = parseResponse('13 OK SEC 01');
      expect(resp.seq, 13);
      expect(resp.verb, Verb.ok);
      expect(resp.okKind, 'SEC');
      expect(resp.level, 0x01);
    });

    test('ERR', () {
      final resp = parseResponse('5 ERR 422 bad_args');
      expect(resp.seq, 5);
      expect(resp.verb, Verb.err);
      expect(resp.errCode, 422);
      expect(resp.errText, 'bad_args');
    });

    test('ERR text may contain spaces', () {
      final resp = parseResponse('5 ERR 503 tool unavailable extra words');
      expect(resp.errCode, 503);
      expect(resp.errText, 'tool unavailable extra words');
    });

    test('PONG', () {
      final resp = parseResponse('2 PONG');
      expect(resp.seq, 2);
      expect(resp.verb, Verb.pong);
    });

    test('EVT (reserved, parses generically)', () {
      final resp = parseResponse('0 EVT something arg1 arg2');
      expect(resp.seq, 0);
      expect(resp.verb, Verb.evt);
      expect(resp.evtName, 'something');
      expect(resp.evtArgs, <String>['arg1', 'arg2']);
    });
  });

  group('parseResponse negative paths', () {
    test('malformed seq throws FormatException', () {
      expect(() => parseResponse('notaseq RSP 00'), throwsFormatException);
    });

    test('missing verb throws FormatException', () {
      expect(() => parseResponse('5'), throwsFormatException);
    });

    test('unknown verb throws FormatException', () {
      expect(() => parseResponse('5 BOGUS'), throwsFormatException);
    });

    test('NRC with wrong arg count throws', () {
      expect(() => parseResponse('5 NRC 27'), throwsFormatException);
      expect(() => parseResponse('5 NRC 27 35 99'), throwsFormatException);
    });

    test('OK with unknown kind throws', () {
      expect(() => parseResponse('5 OK WAT'), throwsFormatException);
    });

    test('OK SEC missing level throws', () {
      expect(() => parseResponse('5 OK SEC'), throwsFormatException);
    });

    test('ERR with missing text throws', () {
      expect(() => parseResponse('5 ERR 422'), throwsFormatException);
    });

    test('RSP with bad hex throws', () {
      expect(() => parseResponse('5 RSP GG'), throwsFormatException);
    });

    test('READY missing field throws', () {
      expect(() => parseResponse('0 READY proto=1 tool=CANoe'),
          throwsFormatException);
    });
  });
}
