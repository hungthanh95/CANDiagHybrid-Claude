// Transport interface (docs/03-TECHNICAL-DETAIL.md §7).
//
// Feature code (DiagService, and later UI/state) depends only on this
// interface, never on a concrete transport such as WsTransport -- mirrors
// the Python `transport_ws` rule (docs/04, CLAUDE.md rule "transport behind
// an interface").
//
// A [Transport] exchanges proto=1 protocol *lines* (without trailing `\n`)
// with the server. Framing (newline-delimited vs. one-message-per-WS-frame)
// is the transport's concern; `lib/protocol/codec.dart` only ever sees full
// lines.

/// Raised when a transport is unavailable, fails to connect, or drops
/// unexpectedly.
class TransportException implements Exception {
  TransportException(this.message);

  final String message;

  @override
  String toString() => 'TransportException: $message';
}

/// A connection to the FlexDiag bridge (or a test double).
abstract class Transport {
  /// Opens the connection.
  ///
  /// Throws [TransportException] if the connection cannot be established.
  Future<void> connect();

  /// Sends one protocol line (no trailing `\n`).
  ///
  /// Throws [TransportException] if not connected, the line exceeds the
  /// protocol's maximum length, or the send fails.
  Future<void> send(String line);

  /// Stream of decoded protocol lines (without trailing `\n`) received from
  /// the server, in order, including unsolicited lines (e.g. the `READY`
  /// banner sent at seq `0`).
  ///
  /// The stream closes (`done`) when the peer closes the connection
  /// cleanly. An unexpected I/O error is delivered as a
  /// [TransportException] error event.
  Stream<String> get lines;

  /// `true` once the connection has been closed (by either side) or has
  /// not yet been opened.
  bool get isClosed;

  /// Closes the connection. Idempotent.
  Future<void> dispose();
}
