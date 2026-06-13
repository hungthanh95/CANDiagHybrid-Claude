// Tests for AppState's bounded auto-reconnect (FR-16, NFR-5), driven via
// FakeAsync + a fake Transport double -- no real WS/bridge needed.
//
// Mirrors `tests/test_terminal_reconnect.py`'s scenarios for the terminal:
// - in-flight requests fail immediately (TransportException) on drop
// - bounded reconnect recovers if a connection becomes available again
// - bounded reconnect exhausts cleanly (no hang, ConnectionStatus.error)
// - reconnect state (status, attempt count) is surfaced via AppState for the
//   connect screen, without screens knowing about WsTransport concretely.

import 'dart:async';

import 'package:fake_async/fake_async.dart';
import 'package:flexdiag_app/state/app_state.dart';
import 'package:flexdiag_app/state/log_entry.dart';
import 'package:flexdiag_app/transport/reconnect_policy.dart';
import 'package:flexdiag_app/transport/transport.dart';
import 'package:flutter_test/flutter_test.dart';

/// In-memory Transport double whose [connect] can be scripted to fail a
/// fixed number of times before succeeding (or to fail forever), via
/// [FakeTransportFactory].
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

  /// Simulates the peer closing the connection / an I/O error.
  void closeStream() {
    _closed = true;
    _controller.close();
  }

  int lastSeq() => int.parse(sent.last.split(' ').first);
}

/// Builds [FakeTransport]s for [AppState]. The first instance (the initial
/// connection) always succeeds; the next [failCount] instances (reconnect
/// attempts) fail [connect], then subsequent instances succeed.
class FakeTransportFactory {
  FakeTransportFactory({this.failCount = 0});

  final int failCount;
  int _created = 0;
  final List<FakeTransport> instances = <FakeTransport>[];

  FakeTransport call(String host, int port) {
    // Instance 0 is the initial connection and always succeeds; reconnect
    // attempts are instances 1.._failCount.
    final failConnect = _created >= 1 && _created <= failCount;
    _created++;
    final t = FakeTransport(failConnect: failConnect);
    instances.add(t);
    return t;
  }
}

/// A [delay] function for [AppState] that records the requested durations
/// and uses a real [Future.delayed] -- under `fakeAsync`, this only resolves
/// once the test advances the fake clock via `async.elapse(...)`, letting
/// tests observe intermediate states (e.g. [ConnectionStatus.reconnecting])
/// between reconnect attempts.
Future<void> Function(Duration) recordingDelay(List<Duration> recorded) {
  return (Duration d) {
    recorded.add(d);
    return Future<void>.delayed(d);
  };
}

void main() {
  group('in-flight request failed immediately on drop', () {
    test('peer closes -> pending DiagService op fails with TransportException '
        'before reconnect completes', () {
      fakeAsync((async) {
        late FakeTransport transport;
        final state = AppState(
          transportFactory: (host, port) {
            transport = FakeTransport();
            return transport;
          },
          reconnectPolicy: const ReconnectPolicy(maxAttempts: 0),
          delay: recordingDelay(<Duration>[]),
        );

        unawaited(state.connect('127.0.0.1', 18770));
        async.flushMicrotasks();
        expect(state.status, ConnectionStatus.connected);

        Object? error;
        unawaited(
          state.diagService!.ping().then(
            (_) {},
            onError: (Object e) => error = e,
          ),
        );
        async.flushMicrotasks();

        // Drop the connection.
        transport.closeStream();
        async.flushMicrotasks();

        expect(error, isA<TransportException>());
      });
    });
  });

  group('bounded reconnect recovers', () {
    test('reconnects after a drop and resumes normal operation', () {
      fakeAsync((async) {
        final factory = FakeTransportFactory(failCount: 0);
        final delays = <Duration>[];
        final state = AppState(
          transportFactory: factory.call,
          reconnectPolicy: const ReconnectPolicy(
            maxAttempts: 5,
            baseDelay: Duration(milliseconds: 10),
            maxDelay: Duration(milliseconds: 50),
          ),
          delay: recordingDelay(delays),
        );

        unawaited(state.connect('127.0.0.1', 18770));
        async.flushMicrotasks();
        expect(state.status, ConnectionStatus.connected);

        // Drop the connection.
        factory.instances.first.closeStream();
        async.flushMicrotasks();

        expect(state.status, ConnectionStatus.reconnecting);

        // The reconnect loop's first (and only, since failCount=0) attempt
        // succeeds after the backoff delay elapses.
        async.elapse(const Duration(milliseconds: 10));

        expect(state.status, ConnectionStatus.connected);
        expect(factory.instances, hasLength(2));
        expect(state.reconnectAttempt, 0);

        final logged = state.log.any(
          (e) =>
              e.direction == LogDirection.info &&
              e.text.contains('reconnected to'),
        );
        expect(logged, isTrue);
      });
    });
  });

  group('bounded reconnect exhausts cleanly', () {
    test('all attempts fail -> ConnectionStatus.error, no hang, no crash', () {
      fakeAsync((async) {
        final factory = FakeTransportFactory(failCount: 100);
        final delays = <Duration>[];
        final state = AppState(
          transportFactory: factory.call,
          reconnectPolicy: const ReconnectPolicy(
            maxAttempts: 3,
            baseDelay: Duration(milliseconds: 10),
            maxDelay: Duration(milliseconds: 20),
          ),
          delay: recordingDelay(delays),
        );

        unawaited(state.connect('127.0.0.1', 18770));
        async.flushMicrotasks();
        expect(state.status, ConnectionStatus.connected);

        factory.instances.first.closeStream();
        async.flushMicrotasks();
        expect(state.status, ConnectionStatus.reconnecting);

        // Drain the reconnect loop: 3 attempts at 10ms/20ms/20ms backoff,
        // each followed by a failing `connect()`.
        async.elapse(const Duration(milliseconds: 100));

        expect(state.status, ConnectionStatus.error);
        expect(state.diagService, isNull);
        // 3 reconnect attempts -> 3 additional failed transports beyond
        // the initial connection.
        expect(factory.instances.length, greaterThanOrEqualTo(4));

        final logged = state.log.any(
          (e) =>
              e.direction == LogDirection.info && e.text.contains('exhausted'),
        );
        expect(logged, isTrue);
      });
    });
  });

  group('explicit disconnect cancels reconnection', () {
    test('disconnect() during a pending reconnect leaves state clean', () {
      fakeAsync((async) {
        final factory = FakeTransportFactory(failCount: 100);
        final delays = <Duration>[];
        final state = AppState(
          transportFactory: factory.call,
          reconnectPolicy: const ReconnectPolicy(
            maxAttempts: 5,
            baseDelay: Duration(milliseconds: 10),
            maxDelay: Duration(milliseconds: 20),
          ),
          delay: recordingDelay(delays),
        );

        unawaited(state.connect('127.0.0.1', 18770));
        async.flushMicrotasks();
        expect(state.status, ConnectionStatus.connected);

        factory.instances.first.closeStream();
        async.flushMicrotasks();
        expect(state.status, ConnectionStatus.reconnecting);

        unawaited(state.disconnect());
        async.flushMicrotasks();

        expect(state.status, ConnectionStatus.disconnected);

        // Further reconnect iterations must not resurrect the connection.
        for (var i = 0; i < 10; i++) {
          async.flushMicrotasks();
        }
        expect(state.status, ConnectionStatus.disconnected);
        expect(state.diagService, isNull);
      });
    });
  });
}
