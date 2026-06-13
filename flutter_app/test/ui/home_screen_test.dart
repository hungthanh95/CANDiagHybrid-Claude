// Widget tests for lib/ui/home_screen.dart (docs/03-TECHNICAL-DETAIL.md
// §7): top-level navigation between the connect/session/read-DTC/clear-DTC/
// security/tester-present screens and the log view.

import 'package:flexdiag_app/state/app_state.dart';
import 'package:flexdiag_app/ui/home_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import '../support/fake_transport.dart';

void main() {
  testWidgets('shows the connect screen by default and can switch to '
      'the log tab', (tester) async {
    final state = AppState(transportFactory: (host, port) => FakeTransport());

    await tester.pumpWidget(MaterialApp(home: HomeScreen(appState: state)));

    expect(find.text('Status: Disconnected'), findsOneWidget);

    await tester.tap(find.text('Log'));
    await tester.pumpAndSettle();

    // The log view renders (even if empty before connect, the ListView
    // exists).
    expect(find.byType(ListView), findsOneWidget);
  });

  testWidgets('after connecting, all tabs are reachable', (tester) async {
    final state = AppState(transportFactory: (host, port) => FakeTransport());

    await tester.pumpWidget(MaterialApp(home: HomeScreen(appState: state)));

    await tester.tap(find.widgetWithText(ElevatedButton, 'Connect'));
    await tester.pumpAndSettle();
    expect(find.text('Status: Connected'), findsOneWidget);

    for (final label in [
      'Session',
      'Read DTC',
      'Clear DTC',
      'Security',
      'Tester Present',
      'Log',
    ]) {
      await tester.tap(find.text(label));
      await tester.pumpAndSettle();
      expect(find.text(label), findsAtLeastNWidgets(1));
    }
  });
}
