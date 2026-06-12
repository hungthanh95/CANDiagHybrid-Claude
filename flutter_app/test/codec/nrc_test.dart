// Tests for lib/codec/nrc.dart -- NRC name table per
// docs/03-TECHNICAL-DETAIL.md §6.2. Mirrors protocol/nrc.py.

import 'package:flexdiag_app/codec/nrc.dart';
import 'package:test/test.dart';

void main() {
  group('nrcName', () {
    test('known codes map to symbolic names', () {
      expect(nrcName(0x10), 'generalReject');
      expect(nrcName(0x11), 'serviceNotSupported');
      expect(nrcName(0x12), 'subFunctionNotSupported');
      expect(nrcName(0x13), 'incorrectMessageLengthOrInvalidFormat');
      expect(nrcName(0x22), 'conditionsNotCorrect');
      expect(nrcName(0x31), 'requestOutOfRange');
      expect(nrcName(0x33), 'securityAccessDenied');
      expect(nrcName(0x35), 'invalidKey');
      expect(nrcName(0x36), 'exceedNumberOfAttempts');
      expect(nrcName(0x37), 'requiredTimeDelayNotExpired');
      expect(nrcName(0x78), 'responsePending');
      expect(nrcName(0x7E), 'subFunctionNotSupportedInActiveSession');
      expect(nrcName(0x7F), 'serviceNotSupportedInActiveSession');
    });

    test('unknown codes render as unknown_XX (uppercase hex)', () {
      expect(nrcName(0x99), 'unknown_99');
      expect(nrcName(0x00), 'unknown_00');
    });
  });
}
