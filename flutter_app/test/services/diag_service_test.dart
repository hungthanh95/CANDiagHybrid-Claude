// Tests for lib/services/diag_service.dart, driven against a fake
// in-memory Transport double (docs/03-TECHNICAL-DETAIL.md §7). No real
// WS/bridge needed.
//
// DiagService depends only on the Transport interface (constraint: never on
// WsTransport concretely).

import 'dart:async';

import 'package:flexdiag_app/services/diag_service.dart';
import 'package:flexdiag_app/transport/transport.dart';
import 'package:test/test.dart';

/// In-memory Transport double. Records every line sent via [sent] and lets
/// the test inject response lines via [pushLine] / [pushError] /
/// [closeStream].
class FakeTransport implements Transport {
  final List<String> sent = <String>[];
  final StreamController<String> _controller =
      StreamController<String>.broadcast();
  bool _closed = false;
  bool connected = false;

  @override
  bool get isClosed => _closed;

  @override
  Stream<String> get lines => _controller.stream;

  @override
  Future<void> connect() async {
    connected = true;
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

void main() {
  late FakeTransport transport;
  late DiagService service;

  setUp(() async {
    transport = FakeTransport();
    service = DiagService(transport);
    await transport.connect();
    service.start();
  });

  tearDown(() async {
    await service.dispose();
  });

  group('readDtc', () {
    test('sends READDTC FF by default and decodes the RSP', () async {
      final future = service.readDtc();
      await Future<void>.delayed(Duration.zero);
      expect(transport.sent.last, endsWith('READDTC FF'));
      final seq = transport.lastSeq();

      transport.pushLine('$seq RSP 59 02 FF 00 12 34 2F 00 56 78 08');

      final result = await future;
      expect(result.availabilityMask, 0xFF);
      expect(result.dtcs, hasLength(2));
      expect(result.dtcs[0].code, 'P01234');
      expect(result.dtcs[1].code, 'P05678');
    });

    test('honours an explicit mask', () async {
      final future = service.readDtc(mask: 0x2F);
      await Future<void>.delayed(Duration.zero);
      expect(transport.sent.last, endsWith('READDTC 2F'));
      final seq = transport.lastSeq();
      transport.pushLine('$seq RSP 59 02 2F');
      await future;
    });

    test('NRC surfaces as NrcException, not DiagErrException', () async {
      final future = service.readDtc();
      await Future<void>.delayed(Duration.zero);
      final seq = transport.lastSeq();
      transport.pushLine('$seq NRC 19 31');

      await expectLater(future, throwsA(isA<NrcException>()));
    });
  });

  group('clearDtc', () {
    test('sends CLEARDTC and returns positive RSP bytes', () async {
      final future = service.clearDtc();
      await Future<void>.delayed(Duration.zero);
      expect(transport.sent.last, endsWith('CLEARDTC'));
      final seq = transport.lastSeq();
      transport.pushLine('$seq RSP 54');

      expect(await future, <int>[0x54]);
    });
  });

  group('session', () {
    test('sends SESSION <hex> and returns positive RSP bytes', () async {
      final future = service.session(0x03);
      await Future<void>.delayed(Duration.zero);
      expect(transport.sent.last, endsWith('SESSION 03'));
      final seq = transport.lastSeq();
      transport.pushLine('$seq RSP 50 03 00 32 01 F4');

      expect(await future, <int>[0x50, 0x03, 0x00, 0x32, 0x01, 0xF4]);
    });
  });

  group('securityUnlock', () {
    test(
      'sends SECURITY <hex> and resolves to the odd level on OK SEC',
      () async {
        final future = service.securityUnlock(0x01);
        await Future<void>.delayed(Duration.zero);
        expect(transport.sent.last, endsWith('SECURITY 01'));
        final seq = transport.lastSeq();
        transport.pushLine('$seq OK SEC 01');

        expect(await future, 0x01);
      },
    );

    test(
      'invalidKey (NRC 27 35) surfaces as NrcException, key not derived',
      () async {
        final future = service.securityUnlock(0x01);
        await Future<void>.delayed(Duration.zero);
        final seq = transport.lastSeq();
        transport.pushLine('$seq NRC 27 35');

        final err = await future.then<Object>(
          (v) => v,
          onError: (Object e) => e,
        );
        expect(err, isA<NrcException>());
        final nrcErr = err as NrcException;
        expect(nrcErr.sid, 0x27);
        expect(nrcErr.nrc, 0x35);
      },
    );

    test('securityAccessDenied (NRC 27 33) surfaces as NrcException', () async {
      final future = service.securityUnlock(0x01);
      await Future<void>.delayed(Duration.zero);
      final seq = transport.lastSeq();
      transport.pushLine('$seq NRC 27 33');

      await expectLater(future, throwsA(isA<NrcException>()));
    });
  });

  group('testerPresent', () {
    test('TP START -> OK TP resolves', () async {
      final future = service.testerPresent(true);
      await Future<void>.delayed(Duration.zero);
      expect(transport.sent.last, endsWith('TP START'));
      final seq = transport.lastSeq();
      transport.pushLine('$seq OK TP');
      await future;
    });

    test('TP STOP -> OK TP resolves', () async {
      final future = service.testerPresent(false);
      await Future<void>.delayed(Duration.zero);
      expect(transport.sent.last, endsWith('TP STOP'));
      final seq = transport.lastSeq();
      transport.pushLine('$seq OK TP');
      await future;
    });
  });

  group('raw', () {
    test('sends RAW <hex> and returns positive RSP bytes', () async {
      final future = service.raw(<int>[0x22, 0xF1, 0x90]);
      await Future<void>.delayed(Duration.zero);
      expect(transport.sent.last, endsWith('RAW 22 F1 90'));
      final seq = transport.lastSeq();
      transport.pushLine('$seq RSP 62 F1 90 56 49 4E');

      expect(await future, <int>[0x62, 0xF1, 0x90, 0x56, 0x49, 0x4E]);
    });
  });

  group('ping', () {
    test('sends PING and resolves on PONG', () async {
      final future = service.ping();
      await Future<void>.delayed(Duration.zero);
      expect(transport.sent.last, endsWith('PING'));
      final seq = transport.lastSeq();
      transport.pushLine('$seq PONG');
      await future;
    });
  });

  group('ERR mapping', () {
    test('ERR 422 bad_args maps to ErrException with code 422', () async {
      final future = service.raw(<int>[0x22, 0xF1, 0x90]);
      await Future<void>.delayed(Duration.zero);
      final seq = transport.lastSeq();
      transport.pushLine('$seq ERR 422 bad_args');

      final err = await future.then<Object>((v) => v, onError: (Object e) => e);
      expect(err, isA<ErrException>());
      final errEx = err as ErrException;
      expect(errEx.code, 422);
      expect(errEx.text, 'bad_args');
    });

    test('ERR 500 keygen_fail maps to ErrException with code 500', () async {
      final future = service.securityUnlock(0x01);
      await Future<void>.delayed(Duration.zero);
      final seq = transport.lastSeq();
      transport.pushLine('$seq ERR 500 keygen_fail');

      final err = await future.then<Object>((v) => v, onError: (Object e) => e);
      expect(err, isA<ErrException>());
      expect((err as ErrException).code, 500);
    });

    test(
      'ERR 503 tool_unavailable maps to ErrException with code 503',
      () async {
        final future = service.ping();
        await Future<void>.delayed(Duration.zero);
        final seq = transport.lastSeq();
        transport.pushLine('$seq ERR 503 tool_unavailable');

        final err = await future.then<Object?>(
          (_) => null,
          onError: (Object e) => e,
        );
        expect(err, isA<ErrException>());
        expect((err as ErrException).code, 503);
      },
    );

    test('ERR 504 ecu_timeout maps to ErrException with code 504', () async {
      final future = service.readDtc();
      await Future<void>.delayed(Duration.zero);
      final seq = transport.lastSeq();
      transport.pushLine('$seq ERR 504 ecu_timeout');

      final err = await future.then<Object>((v) => v, onError: (Object e) => e);
      expect(err, isA<ErrException>());
      expect((err as ErrException).code, 504);
    });
  });

  group('transport drop mid-request', () {
    test(
      'peer closes before responding -> TransportException, no hang',
      () async {
        final future = service.readDtc();
        await Future<void>.delayed(Duration.zero);

        transport.closeStream();

        await expectLater(future, throwsA(isA<TransportException>()));
      },
    );
  });

  group('malformed response line', () {
    test(
      'unparseable line from server is ignored, pending request still resolves',
      () async {
        final future = service.ping();
        await Future<void>.delayed(Duration.zero);
        final seq = transport.lastSeq();

        // Garbage line (e.g. a corrupted/unknown verb) must not crash the
        // service or resolve the pending future incorrectly.
        transport.pushLine('not a valid line');
        transport.pushLine('$seq PONG');

        await future;
      },
    );
  });
}
