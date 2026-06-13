// Widget tests for lib/ui/log_view.dart (docs/03-TECHNICAL-DETAIL.md §7):
// running list of sent/received protocol lines, with NRC/ERR rendered
// distinctly.

import 'package:flexdiag_app/state/app_state.dart';
import 'package:flexdiag_app/ui/log_view.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import '../support/fake_transport.dart';
import '../support/pump.dart';

void main() {
  testWidgets('accumulates sent/received lines as they happen', (tester) async {
    late FakeTransport transport;
    final state = AppState(
      transportFactory: (host, port) {
        transport = FakeTransport();
        return transport;
      },
    );
    await state.connect('127.0.0.1', 18770);

    await tester.pumpWidget(
      wrapScreen(state, (context) => LogView(appState: state)),
    );

    // The "connected to ..." info entry from connect() is already present.
    expect(find.textContaining('connected to 127.0.0.1:18770'), findsOneWidget);

    final future = state.clearDtc();
    await tester.pump();
    final seq = transport.lastSeq();
    expect(find.textContaining('$seq CLEARDTC'), findsOneWidget);

    transport.pushLine('$seq RSP 54');
    await future;
    await tester.pumpAndSettle();

    expect(find.textContaining('$seq RSP 54'), findsOneWidget);
  });

  testWidgets('NRC and ERR entries are styled distinctly', (tester) async {
    late FakeTransport transport;
    final state = AppState(
      transportFactory: (host, port) {
        transport = FakeTransport();
        return transport;
      },
    );
    await state.connect('127.0.0.1', 18770);

    await tester.pumpWidget(
      wrapScreen(state, (context) => LogView(appState: state)),
    );

    final future1 = state.clearDtc();
    await tester.pump();
    transport.pushLine('${transport.lastSeq()} NRC 14 22');
    await future1;
    await tester.pumpAndSettle();

    final future2 = state.session(0x99);
    await tester.pump();
    transport.pushLine('${transport.lastSeq()} ERR 422 bad_args');
    await future2;
    await tester.pumpAndSettle();

    final nrcText = tester.widget<Text>(
      find.text('! NRC 14 22 (conditionsNotCorrect)'),
    );
    final errText = tester.widget<Text>(find.text('! ERR 422 bad_args'));

    expect(nrcText.style?.color, isNotNull);
    expect(errText.style?.color, isNotNull);
    expect(nrcText.style?.color, isNot(errText.style?.color));
  });
}
