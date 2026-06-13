// Shared in-memory Transport double for state/UI tests
// (docs/03-TECHNICAL-DETAIL.md §7). Mirrors
// test/services/diag_service_test.dart's FakeTransport.

import 'dart:async';

import 'package:flexdiag_app/transport/transport.dart';

/// In-memory Transport double. Records every line sent via [sent] and lets
/// the test inject response lines via [pushLine] / [pushError] /
/// [closeStream].
class FakeTransport implements Transport {
  FakeTransport({this.failConnect = false});

  /// If `true`, [connect] throws [TransportException].
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

  /// Injects a response line as if received from the server.
  void pushLine(String line) => _controller.add(line);

  /// Injects a transport-level error (e.g. a malformed/oversized line).
  void pushError(Object error) => _controller.addError(error);

  /// Simulates the peer closing the connection.
  void closeStream() {
    _closed = true;
    _controller.close();
  }

  /// The seq of the most recently sent line.
  int lastSeq() => int.parse(sent.last.split(' ').first);
}

/// Builds an [AppState]-style transport factory backed by [FakeTransport],
/// capturing the most recently created instance via [onCreate].
typedef TransportFactoryFn = FakeTransport Function(String host, int port);
