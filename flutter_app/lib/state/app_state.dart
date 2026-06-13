// App-level state (docs/03-TECHNICAL-DETAIL.md §7): connection lifecycle,
// running log, and the result of the last operation per screen.
//
// Screens depend ONLY on this `ChangeNotifier` (and the `DiagService`/
// `Transport` types it exposes), never construct `WsTransport` directly --
// the transport is created here (via an injectable factory, so tests can
// supply a fake) and wrapped in a `LoggingTransport` before being handed to
// `DiagService`.

import 'dart:async';

import 'package:flutter/foundation.dart';

import '../codec/dtc.dart';
import '../protocol/codec.dart';
import '../services/diag_service.dart';
import '../transport/transport.dart';
import '../transport/ws_transport.dart';
import 'log_entry.dart';
import 'logging_transport.dart';

/// The unsolicited `READY proto=<n> tool=<name> transport=<A|B>` banner sent
/// at seq `0` on connect (docs/03 §1.1). Captured for display on the connect
/// screen -- `DiagService` itself ignores seq-0 lines.
class ReadyInfo {
  const ReadyInfo({
    required this.proto,
    required this.tool,
    required this.transport,
  });

  final int proto;
  final String tool;
  final String transport;
}

/// Connection lifecycle status.
enum ConnectionStatus { disconnected, connecting, connected, error }

/// Result of the last [AppState.securityUnlock] call.
///
/// Distinct subtypes for success / ECU negative response / tool error so
/// the UI can render `OK SEC <level>`, `NRC 27 35`, and `ERR <code> <text>`
/// differently -- "NRC ≠ ERR" (CLAUDE.md rule).
abstract class SecurityResult {
  const SecurityResult();
}

/// `OK SEC <level>` -- the unit is unlocked at [level].
class SecuritySuccess extends SecurityResult {
  const SecuritySuccess(this.level);

  final int level;
}

/// `NRC <sid> <nrc>` -- the unlock failed; the unit is NOT unlocked.
class SecurityNrc extends SecurityResult {
  const SecurityNrc(this.sid, this.nrc);

  final int sid;
  final int nrc;
}

/// `ERR <code> <text>` -- a tool-side error (e.g. `500 keygen_fail`).
class SecurityErr extends SecurityResult {
  const SecurityErr(this.code, this.text);

  final int code;
  final String text;
}

/// Signature for creating a [Transport] for a given host/port. Defaults to
/// [WsTransport]; tests inject a fake.
typedef TransportFactory = Transport Function(String host, int port);

/// Single app-wide state object, held via [ChangeNotifier].
///
/// Construct once (e.g. in `main.dart`) and pass down to screens. Screens
/// must depend only on this class (and the `Transport`/`DiagService`
/// interfaces it exposes) -- never construct `WsTransport` themselves.
class AppState extends ChangeNotifier {
  AppState({TransportFactory? transportFactory})
    : _transportFactory =
          transportFactory ??
          ((host, port) => WsTransport(host: host, port: port));

  final TransportFactory _transportFactory;

  Transport? _transport;
  DiagService? _diagService;
  ConnectionStatus _status = ConnectionStatus.disconnected;

  final List<LogEntry> _log = <LogEntry>[];

  ReadDtcResult? _lastDtcResult;
  List<int>? _lastClearDtcResult;
  List<int>? _lastSessionResult;
  SecurityResult? _lastSecurityResult;
  bool _tpEnabled = false;
  ReadyInfo? _readyInfo;

  /// Current connection status.
  ConnectionStatus get status => _status;

  /// The active [DiagService], or `null` if not connected. Screens use this
  /// to issue requests.
  DiagService? get diagService => _diagService;

  /// Running log of sent/received protocol lines and status messages, in
  /// order (oldest first).
  List<LogEntry> get log => List<LogEntry>.unmodifiable(_log);

  /// Result of the last [readDtc] call, or `null` if none has completed.
  ReadDtcResult? get lastDtcResult => _lastDtcResult;

  /// Raw positive response bytes from the last [clearDtc] call, or `null`.
  List<int>? get lastClearDtcResult => _lastClearDtcResult;

  /// Raw positive response bytes from the last [session] call, or `null`.
  List<int>? get lastSessionResult => _lastSessionResult;

  /// Result of the last [securityUnlock] call, or `null`.
  SecurityResult? get lastSecurityResult => _lastSecurityResult;

  /// `true` if the last [setTesterPresent] call enabled tester present.
  bool get tpEnabled => _tpEnabled;

  /// The most recent `READY` banner (proto/tool/transport), or `null` if
  /// none has been received yet on this connection.
  ReadyInfo? get readyInfo => _readyInfo;

  void _appendLog(LogDirection direction, String text) {
    _log.add(LogEntry(direction: direction, text: text));
    if (direction == LogDirection.recv) {
      _tryCaptureReady(text);
    }
    notifyListeners();
  }

  /// Parses [line] as a `READY` banner (seq `0`) and stores it in
  /// [readyInfo] if it matches; otherwise does nothing. `DiagService` itself
  /// discards seq-0 lines, so this is the only place the banner is observed.
  void _tryCaptureReady(String line) {
    try {
      final resp = parseResponse(line);
      if (resp.seq == 0 &&
          resp.verb == Verb.ready &&
          resp.proto != null &&
          resp.tool != null &&
          resp.transport != null) {
        _readyInfo = ReadyInfo(
          proto: resp.proto!,
          tool: resp.tool!,
          transport: resp.transport!,
        );
      }
    } on ProtocolError {
      // Not a parseable response line -- ignore (mirrors DiagService).
    }
  }

  /// Connects to the bridge at `ws://host:port/`.
  ///
  /// On success, [status] becomes [ConnectionStatus.connected] and
  /// [diagService] is non-null. On failure, [status] becomes
  /// [ConnectionStatus.error] and [diagService] stays `null`.
  Future<void> connect(String host, int port) async {
    _status = ConnectionStatus.connecting;
    notifyListeners();

    final transport = _transportFactory(host, port);
    final logging = LoggingTransport(transport, _appendLog);
    try {
      await logging.connect();
    } catch (e) {
      _status = ConnectionStatus.error;
      _appendLog(LogDirection.info, 'connect to $host:$port failed: $e');
      return;
    }

    final service = DiagService(logging);
    service.start();

    _transport = logging;
    _diagService = service;
    _status = ConnectionStatus.connected;
    _appendLog(LogDirection.info, 'connected to $host:$port');
  }

  /// Disconnects and resets connection-derived state. Idempotent.
  Future<void> disconnect() async {
    final service = _diagService;
    final transport = _transport;
    _diagService = null;
    _transport = null;
    _status = ConnectionStatus.disconnected;
    _readyInfo = null;
    notifyListeners();

    if (service != null) {
      await service.dispose();
    }
    if (transport != null) {
      await transport.dispose();
    }
    _appendLog(LogDirection.info, 'disconnected');
  }

  DiagService _requireService() {
    final service = _diagService;
    if (service == null) {
      throw StateError('not connected');
    }
    return service;
  }

  /// `0x10 <sessionId>` -- diagnostic session control. Stores the raw
  /// positive response in [lastSessionResult].
  Future<void> session(int sessionId) async {
    final service = _requireService();
    try {
      _lastSessionResult = await service.session(sessionId);
      notifyListeners();
    } on NrcException catch (e) {
      _appendLog(LogDirection.nrc, 'NRC ${_hex2(e.sid)} ${_hex2(e.nrc)}');
    } on ErrException catch (e) {
      _appendLog(LogDirection.err, 'ERR ${e.code} ${e.text}');
    }
  }

  /// `0x19 02 <mask>` -- Read DTCs by status mask. Stores the decoded result
  /// in [lastDtcResult].
  Future<void> readDtc({int mask = 0xFF}) async {
    final service = _requireService();
    try {
      _lastDtcResult = await service.readDtc(mask: mask);
      notifyListeners();
    } on NrcException catch (e) {
      _appendLog(LogDirection.nrc, 'NRC ${_hex2(e.sid)} ${_hex2(e.nrc)}');
    } on ErrException catch (e) {
      _appendLog(LogDirection.err, 'ERR ${e.code} ${e.text}');
    }
  }

  /// `0x14 FF FF FF` -- full clear DTC. Stores the raw positive response
  /// bytes in [lastClearDtcResult].
  Future<void> clearDtc() async {
    final service = _requireService();
    try {
      _lastClearDtcResult = await service.clearDtc();
      notifyListeners();
    } on NrcException catch (e) {
      _appendLog(LogDirection.nrc, 'NRC ${_hex2(e.sid)} ${_hex2(e.nrc)}');
    } on ErrException catch (e) {
      _appendLog(LogDirection.err, 'ERR ${e.code} ${e.text}');
    }
  }

  /// `0x27` seed/key security unlock at [level]. Stores the outcome in
  /// [lastSecurityResult] as a [SecuritySuccess], [SecurityNrc], or
  /// [SecurityErr] -- never throws.
  Future<void> securityUnlock(int level) async {
    final service = _requireService();
    try {
      final unlocked = await service.securityUnlock(level);
      _lastSecurityResult = SecuritySuccess(unlocked);
      notifyListeners();
    } on NrcException catch (e) {
      _lastSecurityResult = SecurityNrc(e.sid, e.nrc);
      _appendLog(LogDirection.nrc, 'NRC ${_hex2(e.sid)} ${_hex2(e.nrc)}');
      notifyListeners();
    } on ErrException catch (e) {
      _lastSecurityResult = SecurityErr(e.code, e.text);
      _appendLog(LogDirection.err, 'ERR ${e.code} ${e.text}');
      notifyListeners();
    }
  }

  /// `TP START` / `TP STOP`. Updates [tpEnabled] on `OK TP`.
  Future<void> setTesterPresent(bool enable) async {
    final service = _requireService();
    try {
      await service.testerPresent(enable);
      _tpEnabled = enable;
      notifyListeners();
    } on NrcException catch (e) {
      _appendLog(LogDirection.nrc, 'NRC ${_hex2(e.sid)} ${_hex2(e.nrc)}');
    } on ErrException catch (e) {
      _appendLog(LogDirection.err, 'ERR ${e.code} ${e.text}');
    }
  }

  @override
  void dispose() {
    unawaited(disconnect());
    super.dispose();
  }
}

String _hex2(int v) => v.toRadixString(16).toUpperCase().padLeft(2, '0');
