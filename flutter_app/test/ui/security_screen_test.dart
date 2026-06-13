// Widget tests for lib/ui/security_screen.dart
// (docs/03-TECHNICAL-DETAIL.md §7): single unlock action for a chosen odd
// level, showing `OK SEC <level>` or `NRC 27 35` -- "NRC ≠ ERR" rendered
// distinctly from `ERR`.

import 'package:flexdiag_app/state/app_state.dart';
import 'package:flexdiag_app/ui/security_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import '../support/fake_transport.dart';
import '../support/pump.dart';

void main() {
  testWidgets('successful unlock shows OK SEC <level>', (tester) async {
    late FakeTransport transport;
    final state = AppState(
      transportFactory: (host, port) {
        transport = FakeTransport();
        return transport;
      },
    );
    await state.connect('127.0.0.1', 18770);

    await tester.pumpWidget(
      wrapScreen(state, (context) => SecurityScreen(appState: state)),
    );

    // Default level is 01.
    await tester.tap(find.widgetWithText(ElevatedButton, 'Unlock'));
    await tester.pump();

    final seq = transport.lastSeq();
    expect(transport.sent.last, endsWith('SECURITY 01'));

    transport.pushLine('$seq OK SEC 01');
    await tester.pumpAndSettle();

    expect(find.textContaining('OK SEC 01'), findsOneWidget);
  });

  testWidgets('invalidKey NRC 27 35 renders distinctly from an ERR', (
    tester,
  ) async {
    late FakeTransport transport;
    final state = AppState(
      transportFactory: (host, port) {
        transport = FakeTransport();
        return transport;
      },
    );
    await state.connect('127.0.0.1', 18770);

    await tester.pumpWidget(
      wrapScreen(state, (context) => SecurityScreen(appState: state)),
    );

    await tester.tap(find.widgetWithText(ElevatedButton, 'Unlock'));
    await tester.pump();
    final seq = transport.lastSeq();

    transport.pushLine('$seq NRC 27 35');
    await tester.pumpAndSettle();

    expect(find.textContaining('NRC 27 35'), findsOneWidget);
    // Must not render as a generic/ERR-styled message.
    expect(find.textContaining('ERR'), findsNothing);

    // The NRC text must use the "nrc" styling, distinct from the "err"
    // styling -- spot-check by colour.
    final textWidget = tester.widget<Text>(find.textContaining('NRC 27 35'));
    expect(textWidget.style?.color, isNot(Colors.red));
  });

  testWidgets('tool error ERR 500 keygen_fail renders distinctly from NRC', (
    tester,
  ) async {
    late FakeTransport transport;
    final state = AppState(
      transportFactory: (host, port) {
        transport = FakeTransport();
        return transport;
      },
    );
    await state.connect('127.0.0.1', 18770);

    await tester.pumpWidget(
      wrapScreen(state, (context) => SecurityScreen(appState: state)),
    );

    await tester.tap(find.widgetWithText(ElevatedButton, 'Unlock'));
    await tester.pump();
    final seq = transport.lastSeq();

    transport.pushLine('$seq ERR 500 keygen_fail');
    await tester.pumpAndSettle();

    expect(find.textContaining('ERR 500 keygen_fail'), findsOneWidget);
    expect(find.textContaining('NRC'), findsNothing);

    final textWidget = tester.widget<Text>(
      find.textContaining('ERR 500 keygen_fail'),
    );
    expect(textWidget.style?.color, Colors.red);
  });
}
