// A [Transport] decorator that reports every sent/received protocol line to
// a callback, for the app-level log view (docs/03-TECHNICAL-DETAIL.md §7).
//
// `DiagService` is never modified to support logging -- instead, AppState
// wraps the real `Transport` before handing it to `DiagService`. This keeps
// "transport behind an interface" intact: `DiagService` still only knows
// about `Transport`.

import 'dart:async';

import '../transport/transport.dart';
import 'log_entry.dart';

/// Wraps [inner], invoking [onLine] with [LogDirection.sent] for every line
/// sent and [LogDirection.recv] for every line received, then delegating to
/// [inner].
class LoggingTransport implements Transport {
  LoggingTransport(this._inner, this._onLine);

  final Transport _inner;
  final void Function(LogDirection direction, String line) _onLine;

  @override
  bool get isClosed => _inner.isClosed;

  @override
  Stream<String> get lines => _inner.lines.map((line) {
    _onLine(LogDirection.recv, line);
    return line;
  });

  @override
  Future<void> connect() => _inner.connect();

  @override
  Future<void> send(String line) async {
    _onLine(LogDirection.sent, line);
    await _inner.send(line);
  }

  @override
  Future<void> dispose() => _inner.dispose();
}
