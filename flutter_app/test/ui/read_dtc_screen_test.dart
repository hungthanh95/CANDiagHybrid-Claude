// Widget tests for lib/ui/read_dtc_screen.dart (docs/03-TECHNICAL-DETAIL.md
// §7): READDTC, decoded DTC list (code + status flags, not raw bytes).

import 'package:flexdiag_app/state/app_state.dart';
import 'package:flexdiag_app/ui/read_dtc_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import '../support/fake_transport.dart';
import '../support/pump.dart';

void main() {
  testWidgets(
    'reads and decodes DTCs, showing code and status, not raw bytes',
    (tester) async {
      late FakeTransport transport;
      final state = AppState(
        transportFactory: (host, port) {
          transport = FakeTransport();
          return transport;
        },
      );
      await state.connect('127.0.0.1', 18770);

      await tester.pumpWidget(
        wrapScreen(state, (context) => ReadDtcScreen(appState: state)),
      );

      await tester.tap(find.widgetWithText(ElevatedButton, 'Read DTCs'));
      await tester.pump();

      final seq = transport.lastSeq();
      expect(transport.sent.last, endsWith('READDTC FF'));

      // P01234 status 0x2F, U05678 status 0x08.
      transport.pushLine('$seq RSP 59 02 FF 00 12 34 2F C0 56 78 08');
      await tester.pumpAndSettle();

      expect(find.textContaining('P01234'), findsOneWidget);
      expect(find.textContaining('U05678'), findsOneWidget);
      // Status byte rendered as hex, not the raw 3-byte DTC bytes.
      expect(find.textContaining('2F'), findsOneWidget);
      expect(find.textContaining('08'), findsOneWidget);
      // Raw payload bytes (e.g. "59 02") must not be the primary display.
      expect(find.textContaining('59 02'), findsNothing);
    },
  );

  testWidgets('empty DTC list shows a "no DTCs" message', (tester) async {
    late FakeTransport transport;
    final state = AppState(
      transportFactory: (host, port) {
        transport = FakeTransport();
        return transport;
      },
    );
    await state.connect('127.0.0.1', 18770);

    await tester.pumpWidget(
      wrapScreen(state, (context) => ReadDtcScreen(appState: state)),
    );

    await tester.tap(find.widgetWithText(ElevatedButton, 'Read DTCs'));
    await tester.pump();
    final seq = transport.lastSeq();

    transport.pushLine('$seq RSP 59 02 FF');
    await tester.pumpAndSettle();

    expect(find.textContaining('No DTCs'), findsOneWidget);
  });
}
