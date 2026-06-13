// Tests for lib/transport/transport.dart (the Transport interface) and
// lib/transport/ws_transport.dart (Option B, docs/03-TECHNICAL-DETAIL.md §7).
//
// WsTransport is exercised against a local dart:io WebSocket echo/banner
// server (software loopback -- no real bridge/Vector needed for this unit
// test). Mirrors terminal/transport_ws.py's framing contract: one protocol
// line (no trailing `\n`) per WS text message.

import 'dart:async';
import 'dart:io';

import 'package:flexdiag_app/transport/transport.dart';
import 'package:flexdiag_app/transport/ws_transport.dart';
import 'package:test/test.dart';

/// Starts a tiny WS server that sends an unsolicited READY banner on
/// connect, then echoes any line it receives prefixed with "echo: ", except
/// the special line "CLOSE" which makes the server close the socket.
Future<HttpServer> _startServer() async {
  final server = await HttpServer.bind('127.0.0.1', 0);
  server.listen((req) async {
    final ws = await WebSocketTransformer.upgrade(req);
    ws.add('0 READY proto=1 tool=CANoe transport=B');
    ws.listen((msg) {
      final line = msg is String ? msg : String.fromCharCodes(msg as List<int>);
      if (line == 'CLOSE') {
        ws.close();
        return;
      }
      ws.add('echo: $line');
    });
  });
  return server;
}

void main() {
  group('WsTransport', () {
    late HttpServer server;

    setUp(() async {
      server = await _startServer();
    });

    tearDown(() async {
      await server.close(force: true);
    });

    test('connects, receives banner, sends and receives lines', () async {
      final Transport transport = WsTransport(
        host: '127.0.0.1',
        port: server.port,
      );
      await transport.connect();

      final lines = <String>[];
      final sub = transport.lines.listen(lines.add);

      await transport.send('1 PING');

      // Wait for both the banner and the echo.
      await Future<void>.delayed(const Duration(milliseconds: 100));
      await sub.cancel();

      expect(lines, contains('0 READY proto=1 tool=CANoe transport=B'));
      expect(lines, contains('echo: 1 PING'));

      await transport.dispose();
    });

    test('isClosed is false after connect, true after dispose', () async {
      final transport = WsTransport(host: '127.0.0.1', port: server.port);
      await transport.connect();
      expect(transport.isClosed, isFalse);
      await transport.dispose();
      expect(transport.isClosed, isTrue);
    });

    test('send after dispose throws TransportException', () async {
      final transport = WsTransport(host: '127.0.0.1', port: server.port);
      await transport.connect();
      await transport.dispose();
      await expectLater(
        transport.send('1 PING'),
        throwsA(isA<TransportException>()),
      );
    });

    test('send before connect throws TransportException', () async {
      final transport = WsTransport(host: '127.0.0.1', port: server.port);
      await expectLater(
        transport.send('1 PING'),
        throwsA(isA<TransportException>()),
      );
    });

    test(
      'connect failure (nothing listening) throws TransportException',
      () async {
        final transport = WsTransport(host: '127.0.0.1', port: 1);
        await expectLater(
          transport.connect(),
          throwsA(isA<TransportException>()),
        );
      },
    );

    test('peer-closed connection ends the lines stream', () async {
      final transport = WsTransport(host: '127.0.0.1', port: server.port);
      await transport.connect();

      final done = Completer<void>();
      transport.lines.listen((_) {}, onDone: done.complete);

      await transport.send('CLOSE');
      await done.future.timeout(const Duration(seconds: 2));
      expect(transport.isClosed, isTrue);
    });
  });
}
