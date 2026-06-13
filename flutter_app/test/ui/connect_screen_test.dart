// Widget tests for lib/ui/connect_screen.dart (docs/03-TECHNICAL-DETAIL.md
// §7), driven against a fake Transport via AppState -- no live bridge.

import 'dart:async';

import 'package:flexdiag_app/state/app_state.dart';
import 'package:flexdiag_app/transport/transport.dart';
import 'package:flexdiag_app/ui/connect_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

class FakeTransport implements Transport {
  FakeTransport({this.failConnect = false});

  final bool failConnect;
  final List<String> sent = <String>[];
  final StreamController<String> _controller =
      StreamController<String>.broadcast();
  bool _closed = true;

  @override
  bool get isClosed => _closed;

  @override
  Stream<String> get lines => _controller.stream;

  @override
  Future<void> connect() async {
    if (failConnect) {
      throw TransportException('connection refused');
    }
    _closed = false;
  }

  @override
  Future<void> send(String line) async {
    if (_closed) throw TransportException('not connected');
    sent.add(line);
  }

  @override
  Future<void> dispose() async {
    _closed = true;
    await _controller.close();
  }

  void pushLine(String line) => _controller.add(line);
}

Widget _wrap(AppState state) {
  return MaterialApp(
    home: Scaffold(
      body: ListenableBuilder(
        listenable: state,
        builder: (context, _) => ConnectScreen(appState: state),
      ),
    ),
  );
}

void main() {
  testWidgets('shows disconnected status and a Connect button', (tester) async {
    final state = AppState(transportFactory: (host, port) => FakeTransport());

    await tester.pumpWidget(_wrap(state));

    expect(find.text('Status: Disconnected'), findsOneWidget);
    expect(find.widgetWithText(ElevatedButton, 'Connect'), findsOneWidget);
  });

  testWidgets('connecting shows connected status and READY info, '
      'then disconnect resets it', (tester) async {
    late FakeTransport transport;
    final state = AppState(
      transportFactory: (host, port) {
        transport = FakeTransport();
        return transport;
      },
    );

    await tester.pumpWidget(_wrap(state));

    await tester.tap(find.widgetWithText(ElevatedButton, 'Connect'));
    await tester.pumpAndSettle();

    expect(find.text('Status: Connected'), findsOneWidget);

    transport.pushLine('0 READY proto=1 tool=mock transport=B');
    await tester.pumpAndSettle();

    expect(find.textContaining('mock'), findsOneWidget);
    expect(find.textContaining('proto=1'), findsOneWidget);

    await tester.tap(find.widgetWithText(ElevatedButton, 'Disconnect'));
    await tester.pumpAndSettle();

    expect(find.text('Status: Disconnected'), findsOneWidget);
  });

  testWidgets('connect failure shows an error status', (tester) async {
    final state = AppState(
      transportFactory: (host, port) => FakeTransport(failConnect: true),
    );

    await tester.pumpWidget(_wrap(state));

    await tester.tap(find.widgetWithText(ElevatedButton, 'Connect'));
    await tester.pumpAndSettle();

    expect(find.text('Status: Error'), findsOneWidget);
  });
}
