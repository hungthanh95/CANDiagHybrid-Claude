// Widget tests for lib/ui/clear_dtc_screen.dart
// (docs/03-TECHNICAL-DETAIL.md §7): single CLEARDTC button, show result.

import 'package:flexdiag_app/state/app_state.dart';
import 'package:flexdiag_app/ui/clear_dtc_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import '../support/fake_transport.dart';
import '../support/pump.dart';

void main() {
  testWidgets('sends CLEARDTC and shows a success result', (tester) async {
    late FakeTransport transport;
    final state = AppState(
      transportFactory: (host, port) {
        transport = FakeTransport();
        return transport;
      },
    );
    await state.connect('127.0.0.1', 18770);

    await tester.pumpWidget(
      wrapScreen(state, (context) => ClearDtcScreen(appState: state)),
    );

    await tester.tap(find.widgetWithText(ElevatedButton, 'Clear DTCs'));
    await tester.pump();

    final seq = transport.lastSeq();
    expect(transport.sent.last, endsWith('CLEARDTC'));

    transport.pushLine('$seq RSP 54');
    await tester.pumpAndSettle();

    expect(find.textContaining('54'), findsOneWidget);
  });

  testWidgets('NRC response renders distinctly from ERR', (tester) async {
    late FakeTransport transport;
    final state = AppState(
      transportFactory: (host, port) {
        transport = FakeTransport();
        return transport;
      },
    );
    await state.connect('127.0.0.1', 18770);

    await tester.pumpWidget(
      wrapScreen(state, (context) => ClearDtcScreen(appState: state)),
    );

    await tester.tap(find.widgetWithText(ElevatedButton, 'Clear DTCs'));
    await tester.pump();
    final seq = transport.lastSeq();

    transport.pushLine('$seq NRC 14 22');
    await tester.pumpAndSettle();

    expect(find.textContaining('NRC 14 22'), findsOneWidget);
  });
}
