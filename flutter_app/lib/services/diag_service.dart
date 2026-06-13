// High-level diagnostic operations (docs/03-TECHNICAL-DETAIL.md §7).
//
// DiagService depends only on the Transport interface (never on
// WsTransport concretely) -- this is the seam screens will use once UI work
// starts. It encodes each verb via lib/protocol/codec.dart, sends it over
// the transport, and correlates the terminal response by seq (mirrors
// terminal/repl.py's `_send_and_wait` / `_read_loop`).
//
// `Diag::*` sysvars are never referenced here -- this is purely WS
// line-protocol on the client side (CAPL/bridge-only, per CLAUDE.md §3.4).

import 'dart:async';

import 'package:flexdiag_app/codec/dtc.dart';

import '../protocol/codec.dart';
import '../protocol/seq.dart';
import '../transport/transport.dart';

/// An ECU negative response (`NRC <sid> <nrc>`). Distinct from
/// [ErrException] -- "NRC ≠ ERR" (docs/03 §1.3, CLAUDE.md rule).
class NrcException implements Exception {
  NrcException(this.sid, this.nrc);

  /// The service id (SID) the request was for.
  final int sid;

  /// The negative response code (e.g. `0x35` invalidKey).
  final int nrc;

  @override
  String toString() =>
      'NrcException(sid=0x${sid.toRadixString(16).toUpperCase().padLeft(2, '0')}, '
      'nrc=0x${nrc.toRadixString(16).toUpperCase().padLeft(2, '0')})';
}

/// A protocol/tool error (`ERR <code> <text>`), per docs/03 §1.5's closed
/// set: `400 unknown_verb`, `422 bad_args`, `500 keygen_fail`,
/// `503 tool_unavailable`, `504 ecu_timeout`.
class ErrException implements Exception {
  ErrException(this.code, this.text);

  final int code;
  final String text;

  @override
  String toString() => 'ErrException($code, $text)';
}

/// Raised when a response line cannot be correlated to any pending request,
/// or other unexpected server-side response shapes are received for a given
/// verb (e.g. `RSP` where `OK SEC` was expected).
class UnexpectedResponseException implements Exception {
  UnexpectedResponseException(this.message);

  final String message;

  @override
  String toString() => 'UnexpectedResponseException: $message';
}

/// High-level diagnostic operations over a [Transport].
///
/// Call [start] once after the transport is connected to begin correlating
/// responses; call [dispose] to stop listening and fail any pending
/// requests.
class DiagService {
  DiagService(this._transport);

  final Transport _transport;
  final SeqAllocator _seqAlloc = SeqAllocator();
  final Map<int, Completer<Response>> _pending = <int, Completer<Response>>{};
  StreamSubscription<String>? _sub;

  /// Begins listening to the transport's line stream and correlating
  /// responses to pending requests by seq. Unsolicited lines (seq `0`,
  /// e.g. `READY`/`EVT`) are ignored at this layer.
  void start() {
    _sub = _transport.lines.listen(_onLine, onError: _onError, onDone: _onDone);
  }

  void _onLine(String line) {
    Response resp;
    try {
      resp = parseResponse(line);
    } on ProtocolError {
      // Unparseable line from server -- ignore, peer stays alive (mirrors
      // terminal/repl.py's _read_loop: log and continue).
      return;
    }
    if (resp.seq == 0) {
      // Unsolicited READY/EVT -- not correlated to a command.
      return;
    }
    final completer = _pending.remove(resp.seq);
    if (completer != null && !completer.isCompleted) {
      completer.complete(resp);
    }
  }

  void _onError(Object error) {
    _failAllPending(
      error is TransportException ? error : TransportException('$error'),
    );
  }

  void _onDone() {
    _failAllPending(TransportException('connection closed'));
  }

  void _failAllPending(TransportException error) {
    for (final completer in _pending.values) {
      if (!completer.isCompleted) {
        completer.completeError(error);
      }
    }
    _pending.clear();
  }

  /// Sends [line] and returns a future that resolves with the terminal
  /// response sharing its seq, or throws [TransportException] if the
  /// connection drops before a response arrives.
  Future<Response> _sendAndWait(String line) async {
    final seq = int.parse(line.split(' ').first);
    final completer = Completer<Response>();
    _pending[seq] = completer;
    try {
      await _transport.send(line);
    } catch (e) {
      _pending.remove(seq);
      rethrow;
    }
    return completer.future;
  }

  /// Throws [NrcException] or [ErrException] if [resp] is a negative
  /// response or protocol error; otherwise returns [resp] unchanged.
  Response _checkNegative(Response resp) {
    if (resp.verb == Verb.nrc) {
      throw NrcException(resp.sid!, resp.nrc!);
    }
    if (resp.verb == Verb.err) {
      throw ErrException(resp.errCode!, resp.errText!);
    }
    return resp;
  }

  /// `0x19 02 <mask>` -- Read DTCs by status mask (default `0xFF`).
  ///
  /// Returns the decoded DTC list. Throws [NrcException] on a negative UDS
  /// response, [ErrException] on a protocol/tool error, or
  /// [TransportException] if the connection drops.
  Future<ReadDtcResult> readDtc({int mask = 0xFF}) async {
    final seq = _seqAlloc.next();
    final resp = _checkNegative(
      await _sendAndWait(encodeReadDtc(seq, mask: mask)),
    );
    if (resp.verb != Verb.rsp || resp.data == null) {
      throw UnexpectedResponseException(
        'readDtc: expected RSP, got ${resp.verb}',
      );
    }
    return parseReadDtcPayload(resp.data!);
  }

  /// `0x14 FF FF FF` -- full clear DTC.
  ///
  /// Returns the raw positive response bytes (e.g. `[0x54]`).
  Future<List<int>> clearDtc() async {
    final seq = _seqAlloc.next();
    final resp = _checkNegative(await _sendAndWait(encodeClearDtc(seq)));
    if (resp.verb != Verb.rsp || resp.data == null) {
      throw UnexpectedResponseException(
        'clearDtc: expected RSP, got ${resp.verb}',
      );
    }
    return resp.data!;
  }

  /// `0x10 <session>` -- diagnostic session control.
  ///
  /// Returns the raw positive response bytes (e.g.
  /// `[0x50, session, ...timing]`). Uses `RSP`, never `OK` (docs/03 §1.3).
  Future<List<int>> session(int sessionId) async {
    final seq = _seqAlloc.next();
    final resp = _checkNegative(
      await _sendAndWait(encodeSession(seq, sessionId)),
    );
    if (resp.verb != Verb.rsp || resp.data == null) {
      throw UnexpectedResponseException(
        'session: expected RSP, got ${resp.verb}',
      );
    }
    return resp.data!;
  }

  /// Full seed/key security unlock at [level] (an odd level, e.g. `0x01`).
  ///
  /// Returns the unlocked (odd) level on success (`OK SEC <level>`).
  /// Throws [NrcException] (e.g. `NRC 27 35` invalidKey, `NRC 27 33`
  /// securityAccessDenied) if the unlock fails -- the unit is NOT unlocked
  /// in that case. Throws [ErrException] (e.g. `ERR 500 keygen_fail`) on a
  /// tool-side key-generation failure.
  Future<int> securityUnlock(int level) async {
    final seq = _seqAlloc.next();
    final resp = _checkNegative(await _sendAndWait(encodeSecurity(seq, level)));
    if (resp.verb != Verb.ok || resp.okKind != 'SEC' || resp.level == null) {
      throw UnexpectedResponseException(
        'securityUnlock: expected OK SEC, got ${resp.verb}',
      );
    }
    return resp.level!;
  }

  /// `TP START` (enable) / `TP STOP` (disable) periodic tester present.
  ///
  /// Resolves on `OK TP`. Seq correlation distinguishes START from STOP
  /// (docs/03 §1.3).
  Future<void> testerPresent(bool enable) async {
    final seq = _seqAlloc.next();
    final line = enable ? encodeTpStart(seq) : encodeTpStop(seq);
    final resp = _checkNegative(await _sendAndWait(line));
    if (resp.verb != Verb.ok || resp.okKind != 'TP') {
      throw UnexpectedResponseException(
        'testerPresent: expected OK TP, got ${resp.verb}',
      );
    }
  }

  /// Sends an arbitrary full UDS request frame and returns the raw positive
  /// response bytes (decoded client-side by callers, no CDD).
  Future<List<int>> raw(List<int> data) async {
    final seq = _seqAlloc.next();
    final resp = _checkNegative(await _sendAndWait(encodeRaw(seq, data)));
    if (resp.verb != Verb.rsp || resp.data == null) {
      throw UnexpectedResponseException('raw: expected RSP, got ${resp.verb}');
    }
    return resp.data!;
  }

  /// Liveness check; resolves on `PONG`.
  Future<void> ping() async {
    final seq = _seqAlloc.next();
    final resp = _checkNegative(await _sendAndWait(encodePing(seq)));
    if (resp.verb != Verb.pong) {
      throw UnexpectedResponseException(
        'ping: expected PONG, got ${resp.verb}',
      );
    }
  }

  /// Stops listening for responses and fails any pending requests with
  /// [TransportException]. Does not close the underlying [Transport] --
  /// callers own the transport lifecycle.
  Future<void> dispose() async {
    await _sub?.cancel();
    _sub = null;
    _failAllPending(TransportException('service disposed'));
  }
}
