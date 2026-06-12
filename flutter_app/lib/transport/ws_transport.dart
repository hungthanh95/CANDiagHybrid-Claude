// Option B transport: WebSocket, line-based proto=1 framing.
//
// Connects to the Python bridge (`bridge/flexdiag_bridge.py`) at
// `ws://host:port/` and exchanges protocol lines, mirroring
// `terminal/transport_ws.py`'s `WsTransport`: one protocol line (without a
// trailing `\n`) per WebSocket text message.

import 'dart:async';

import 'package:web_socket_channel/io.dart';
import 'package:web_socket_channel/web_socket_channel.dart';

import 'transport.dart';

/// proto=1 maximum line length (docs/03-TECHNICAL-DETAIL.md §1.5), mirrored
/// from `lib/protocol/codec.dart`'s `kMaxLine` to avoid a transport <->
/// protocol layering dependency in the wrong direction.
const int _kMaxLine = 4095;

/// Async line-based WebSocket transport for the proto=1 wire protocol
/// (Option B).
class WsTransport implements Transport {
  /// Args:
  ///   host: Server hostname/IP (default `127.0.0.1`).
  ///   port: Server WebSocket port (default `8770`, per CLAUDE.md §5).
  WsTransport({this.host = '127.0.0.1', this.port = 8770});

  final String host;
  final int port;

  WebSocketChannel? _channel;
  bool _closed = true;
  StreamController<String>? _linesController;

  @override
  bool get isClosed => _closed;

  @override
  Stream<String> get lines {
    final controller = _linesController;
    if (controller == null) {
      throw TransportException('not connected');
    }
    return controller.stream;
  }

  @override
  Future<void> connect() async {
    final uri = Uri.parse('ws://$host:$port/');
    final controller = StreamController<String>.broadcast();
    _linesController = controller;
    try {
      final channel = IOWebSocketChannel.connect(uri);
      // Surface connect-time failures (e.g. connection refused) by waiting
      // for the channel to actually be ready.
      await channel.ready;
      _channel = channel;
      _closed = false;
      channel.stream.listen(
        (dynamic raw) {
          final line =
              raw is String ? raw : String.fromCharCodes(raw as List<int>);
          final trimmed = line.replaceAll(RegExp(r'[\r\n]+$'), '');
          if (trimmed.length + 1 > _kMaxLine) {
            _closed = true;
            controller
                .addError(TransportException('line exceeds buffer limit'));
            controller.close();
            return;
          }
          controller.add(trimmed);
        },
        onError: (Object error) {
          _closed = true;
          controller.addError(TransportException('recv failed: $error'));
          controller.close();
        },
        onDone: () {
          _closed = true;
          controller.close();
        },
      );
    } catch (e) {
      _closed = true;
      _channel = null;
      throw TransportException('connect to $uri failed: $e');
    }
  }

  @override
  Future<void> send(String line) async {
    final channel = _channel;
    if (channel == null || _closed) {
      throw TransportException('not connected');
    }
    if (line.length + 1 > _kMaxLine) {
      throw TransportException(
          'line exceeds max length ($_kMaxLine): ${line.length + 1}');
    }
    try {
      channel.sink.add(line);
    } catch (e) {
      _closed = true;
      throw TransportException('send failed: $e');
    }
  }

  @override
  Future<void> dispose() async {
    final channel = _channel;
    if (channel != null && !_closed) {
      await channel.sink.close();
    }
    _closed = true;
    await _linesController?.close();
  }
}
