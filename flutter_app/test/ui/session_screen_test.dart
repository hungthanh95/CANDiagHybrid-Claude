// Widget tests for lib/ui/session_screen.dart (docs/03-TECHNICAL-DETAIL.md
// §7): send `SESSION <hex>`, show the `RSP`.

import 'package:flexdiag_app/state/app_state.dart';
import 'package:flexdiag_app/ui/session_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import '../support/fake_transport.dart';
import '../support/pump.dart';

void main() {
  testWidgets('sends SESSION <hex> and shows the RSP bytes', (tester) async {
    late FakeTransport transport;
    final state = AppState(
      transportFactory: (host, port) {
        transport = FakeTransport();
        return transport;
      },
    );
    await state.connect('127.0.0.1', 18770);

    await tester.pumpWidget(
      wrapScreen(state, (context) => SessionScreen(appState: state)),
    );

    // Default session id field is "03" (extended diagnostic session).
    await tester.tap(find.widgetWithText(ElevatedButton, 'Send'));
    await tester.pump();

    final seq = transport.lastSeq();
    expect(transport.sent.last, endsWith('SESSION 03'));

    transport.pushLine('$seq RSP 50 03 00 32 01 F4');
    await tester.pumpAndSettle();

    expect(find.textContaining('50 03 00 32 01 F4'), findsOneWidget);
  });

  testWidgets('NRC response is rendered distinctly from ERR', (tester) async {
    late FakeTransport transport;
    final state = AppState(
      transportFactory: (host, port) {
        transport = FakeTransport();
        return transport;
      },
    );
    await state.connect('127.0.0.1', 18770);

    await tester.pumpWidget(
      wrapScreen(state, (context) => SessionScreen(appState: state)),
    );

    await tester.tap(find.widgetWithText(ElevatedButton, 'Send'));
    await tester.pump();
    final seq = transport.lastSeq();

    transport.pushLine('$seq NRC 10 12');
    await tester.pumpAndSettle();

    expect(find.textContaining('NRC 10 12'), findsOneWidget);
  });
}
