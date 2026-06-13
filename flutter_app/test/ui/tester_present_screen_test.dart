// Widget tests for lib/ui/tester_present_screen.dart
// (docs/03-TECHNICAL-DETAIL.md §7): on/off toggle, `OK TP`.

import 'package:flexdiag_app/state/app_state.dart';
import 'package:flexdiag_app/ui/tester_present_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import '../support/fake_transport.dart';
import '../support/pump.dart';

void main() {
  testWidgets('toggling on sends TP START, toggling off sends TP STOP', (
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
      wrapScreen(state, (context) => TesterPresentScreen(appState: state)),
    );

    expect(find.byType(Switch), findsOneWidget);
    final initialSwitch = tester.widget<Switch>(find.byType(Switch));
    expect(initialSwitch.value, isFalse);

    await tester.tap(find.byType(Switch));
    await tester.pump();

    var seq = transport.lastSeq();
    expect(transport.sent.last, endsWith('TP START'));
    transport.pushLine('$seq OK TP');
    await tester.pumpAndSettle();

    expect(find.textContaining('OK TP'), findsOneWidget);
    expect(tester.widget<Switch>(find.byType(Switch)).value, isTrue);

    await tester.tap(find.byType(Switch));
    await tester.pump();

    seq = transport.lastSeq();
    expect(transport.sent.last, endsWith('TP STOP'));
    transport.pushLine('$seq OK TP');
    await tester.pumpAndSettle();

    expect(tester.widget<Switch>(find.byType(Switch)).value, isFalse);
  });
}
