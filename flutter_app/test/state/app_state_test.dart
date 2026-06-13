// Tests for lib/state/app_state.dart, driven against a FakeTransport double
// (docs/03-TECHNICAL-DETAIL.md §7). No real WS/bridge needed.
//
// AppState depends only on the Transport interface via an injectable
// transport factory -- never constructs WsTransport directly in tests.

import 'dart:async';

import 'package:flexdiag_app/state/app_state.dart';
import 'package:flexdiag_app/state/log_entry.dart';
import 'package:flexdiag_app/transport/transport.dart';
import 'package:flutter_test/flutter_test.dart';

/// In-memory Transport double (mirrors
/// test/services/diag_service_test.dart's FakeTransport).
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

  int lastSeq() => int.parse(sent.last.split(' ').first);
}

void main() {
  group('connection lifecycle', () {
    test('starts disconnected', () {
      final state = AppState();
      expect(state.status, ConnectionStatus.disconnected);
      expect(state.diagService, isNull);
    });

    test(
      'connect() succeeds -> status connected, logs an info entry',
      () async {
        late FakeTransport transport;
        final state = AppState(
          transportFactory: (host, port) {
            transport = FakeTransport();
            return transport;
          },
        );

        await state.connect('127.0.0.1', 18770);

        expect(state.status, ConnectionStatus.connected);
        expect(state.diagService, isNotNull);
        expect(transport.isClosed, isFalse);
        expect(
          state.log.any(
            (e) =>
                e.direction == LogDirection.info &&
                e.text.contains('connected'),
          ),
          isTrue,
        );
      },
    );

    test('connect() failure -> status error, logs an info entry', () async {
      final state = AppState(
        transportFactory: (host, port) => FakeTransport(failConnect: true),
      );

      await state.connect('127.0.0.1', 18770);

      expect(state.status, ConnectionStatus.error);
      expect(state.diagService, isNull);
      expect(
        state.log.any(
          (e) =>
              e.direction == LogDirection.info &&
              e.text.toLowerCase().contains('fail'),
        ),
        isTrue,
      );
    });

    test('READY banner (seq 0) is captured into readyInfo for the connect '
        'screen', () async {
      late FakeTransport transport;
      final state = AppState(
        transportFactory: (host, port) {
          transport = FakeTransport();
          return transport;
        },
      );
      await state.connect('127.0.0.1', 18770);

      transport.pushLine('0 READY proto=1 tool=mock transport=B');
      await Future<void>.delayed(Duration.zero);

      expect(state.readyInfo, isNotNull);
      expect(state.readyInfo!.proto, 1);
      expect(state.readyInfo!.tool, 'mock');
      expect(state.readyInfo!.transport, 'B');
    });

    test(
      'disconnect() resets to disconnected and disposes the transport',
      () async {
        late FakeTransport transport;
        final state = AppState(
          transportFactory: (host, port) {
            transport = FakeTransport();
            return transport;
          },
        );
        await state.connect('127.0.0.1', 18770);

        await state.disconnect();

        expect(state.status, ConnectionStatus.disconnected);
        expect(state.diagService, isNull);
        expect(transport.isClosed, isTrue);
      },
    );
  });

  group('log view', () {
    test('sent and received lines are appended to the log', () async {
      late FakeTransport transport;
      final state = AppState(
        transportFactory: (host, port) {
          transport = FakeTransport();
          return transport;
        },
      );
      await state.connect('127.0.0.1', 18770);

      final future = state.session(0x03);
      await Future<void>.delayed(Duration.zero);
      final seq = transport.lastSeq();
      expect(
        state.log.any(
          (e) =>
              e.direction == LogDirection.sent && e.text == '$seq SESSION 03',
        ),
        isTrue,
      );

      transport.pushLine('$seq RSP 50 03 00 32 01 F4');
      await future;

      expect(
        state.log.any(
          (e) =>
              e.direction == LogDirection.recv &&
              e.text == '$seq RSP 50 03 00 32 01 F4',
        ),
        isTrue,
      );
    });
  });

  group('session', () {
    test('session() sends SESSION <hex> and stores the RSP', () async {
      late FakeTransport transport;
      final state = AppState(
        transportFactory: (host, port) {
          transport = FakeTransport();
          return transport;
        },
      );
      await state.connect('127.0.0.1', 18770);

      final future = state.session(0x03);
      await Future<void>.delayed(Duration.zero);
      final seq = transport.lastSeq();
      transport.pushLine('$seq RSP 50 03 00 32 01 F4');
      await future;

      expect(state.lastSessionResult, <int>[
        0x50,
        0x03,
        0x00,
        0x32,
        0x01,
        0xF4,
      ]);
    });
  });

  group('readDtc', () {
    test('readDtc() decodes the RSP into lastDtcResult', () async {
      late FakeTransport transport;
      final state = AppState(
        transportFactory: (host, port) {
          transport = FakeTransport();
          return transport;
        },
      );
      await state.connect('127.0.0.1', 18770);

      final future = state.readDtc();
      await Future<void>.delayed(Duration.zero);
      final seq = transport.lastSeq();
      transport.pushLine('$seq RSP 59 02 FF 00 12 34 2F');
      await future;

      expect(state.lastDtcResult, isNotNull);
      expect(state.lastDtcResult!.dtcs, hasLength(1));
      expect(state.lastDtcResult!.dtcs[0].code, 'P01234');
      expect(state.lastDtcResult!.dtcs[0].status, 0x2F);
    });
  });

  group('clearDtc', () {
    test('clearDtc() success records a positive result', () async {
      late FakeTransport transport;
      final state = AppState(
        transportFactory: (host, port) {
          transport = FakeTransport();
          return transport;
        },
      );
      await state.connect('127.0.0.1', 18770);

      final future = state.clearDtc();
      await Future<void>.delayed(Duration.zero);
      final seq = transport.lastSeq();
      transport.pushLine('$seq RSP 54');
      await future;

      expect(state.lastClearDtcResult, <int>[0x54]);
    });
  });

  group('securityUnlock', () {
    test(
      'success: OK SEC <level> -> lastSecurityResult holds the level',
      () async {
        late FakeTransport transport;
        final state = AppState(
          transportFactory: (host, port) {
            transport = FakeTransport();
            return transport;
          },
        );
        await state.connect('127.0.0.1', 18770);

        final future = state.securityUnlock(0x01);
        await Future<void>.delayed(Duration.zero);
        final seq = transport.lastSeq();
        transport.pushLine('$seq OK SEC 01');
        await future;

        expect(state.lastSecurityResult, isA<SecuritySuccess>());
        expect((state.lastSecurityResult as SecuritySuccess).level, 0x01);
      },
    );

    test('invalidKey: NRC 27 35 -> lastSecurityResult is a SecurityNrc, '
        'distinct from a tool ERR', () async {
      late FakeTransport transport;
      final state = AppState(
        transportFactory: (host, port) {
          transport = FakeTransport();
          return transport;
        },
      );
      await state.connect('127.0.0.1', 18770);

      final future = state.securityUnlock(0x01);
      await Future<void>.delayed(Duration.zero);
      final seq = transport.lastSeq();
      transport.pushLine('$seq NRC 27 35');
      await future;

      final result = state.lastSecurityResult;
      expect(result, isA<SecurityNrc>());
      final nrcResult = result as SecurityNrc;
      expect(nrcResult.sid, 0x27);
      expect(nrcResult.nrc, 0x35);

      // The log entry for the NRC must be tagged `LogDirection.nrc`, not
      // `LogDirection.err` -- "NRC ≠ ERR".
      expect(
        state.log.any(
          (e) =>
              e.direction == LogDirection.nrc && e.text.contains('NRC 27 35'),
        ),
        isTrue,
      );
      expect(state.log.any((e) => e.direction == LogDirection.err), isFalse);
    });

    test('tool error: ERR 500 keygen_fail -> lastSecurityResult is a '
        'SecurityErr, tagged err not nrc', () async {
      late FakeTransport transport;
      final state = AppState(
        transportFactory: (host, port) {
          transport = FakeTransport();
          return transport;
        },
      );
      await state.connect('127.0.0.1', 18770);

      final future = state.securityUnlock(0x01);
      await Future<void>.delayed(Duration.zero);
      final seq = transport.lastSeq();
      transport.pushLine('$seq ERR 500 keygen_fail');
      await future;

      final result = state.lastSecurityResult;
      expect(result, isA<SecurityErr>());
      final errResult = result as SecurityErr;
      expect(errResult.code, 500);
      expect(errResult.text, 'keygen_fail');

      expect(
        state.log.any(
          (e) =>
              e.direction == LogDirection.err &&
              e.text.contains('ERR 500 keygen_fail'),
        ),
        isTrue,
      );
      expect(state.log.any((e) => e.direction == LogDirection.nrc), isFalse);
    });
  });

  group('testerPresent', () {
    test('testerPresent(true) -> OK TP sets tpEnabled true', () async {
      late FakeTransport transport;
      final state = AppState(
        transportFactory: (host, port) {
          transport = FakeTransport();
          return transport;
        },
      );
      await state.connect('127.0.0.1', 18770);

      final future = state.setTesterPresent(true);
      await Future<void>.delayed(Duration.zero);
      final seq = transport.lastSeq();
      transport.pushLine('$seq OK TP');
      await future;

      expect(state.tpEnabled, isTrue);
    });

    test('testerPresent(false) -> OK TP sets tpEnabled false', () async {
      late FakeTransport transport;
      final state = AppState(
        transportFactory: (host, port) {
          transport = FakeTransport();
          return transport;
        },
      );
      await state.connect('127.0.0.1', 18770);

      var future = state.setTesterPresent(true);
      await Future<void>.delayed(Duration.zero);
      transport.pushLine('${transport.lastSeq()} OK TP');
      await future;
      expect(state.tpEnabled, isTrue);

      future = state.setTesterPresent(false);
      await Future<void>.delayed(Duration.zero);
      transport.pushLine('${transport.lastSeq()} OK TP');
      await future;
      expect(state.tpEnabled, isFalse);
    });
  });

  group('notifications', () {
    test('AppState notifies listeners on state changes', () async {
      late FakeTransport transport;
      final state = AppState(
        transportFactory: (host, port) {
          transport = FakeTransport();
          return transport;
        },
      );
      var notifications = 0;
      state.addListener(() => notifications++);

      await state.connect('127.0.0.1', 18770);
      expect(notifications, greaterThan(0));

      final before = notifications;
      final future = state.clearDtc();
      await Future<void>.delayed(Duration.zero);
      transport.pushLine('${transport.lastSeq()} RSP 54');
      await future;
      expect(notifications, greaterThan(before));
    });
  });
}
