// Wire-protocol codec for FlexDiag proto=1.
//
// Implements the line-based ASCII protocol from
// docs/03-TECHNICAL-DETAIL.md §1: one message per line,
// `<SEQ> <VERB> [args...]`, hex bytes uppercase space-separated with no `0x`
// prefix.
//
// This module is the single parser/encoder for the protocol in Dart (mirrors
// `protocol/wire.py` -- docs/04 §1 "one protocol parser per language").
// Lines are returned/accepted WITHOUT the trailing `\n`; the transport layer
// is responsible for framing (see `transport/ws_transport.dart`).

/// proto=1, per docs/03 §1.
const int kProto = 1;

/// Maximum line length in bytes (matches `kMaxLen` in `flexdiag_core.can`
/// and the RAW byte payload cap, docs/03 §1.5).
const int kMaxLine = 4095;

/// Protocol verbs (docs/03 §1.2 client->server, §1.3 server->client).
///
/// Values are the literal uppercase wire tokens.
class Verb {
  // Client -> server
  static const String hello = 'HELLO';
  static const String session = 'SESSION';
  static const String readDtc = 'READDTC';
  static const String clearDtc = 'CLEARDTC';
  static const String security = 'SECURITY';
  static const String tp = 'TP';
  static const String raw = 'RAW';
  static const String ping = 'PING';
  static const String bye = 'BYE';

  // Server -> client
  static const String ready = 'READY';
  static const String rsp = 'RSP';
  static const String nrc = 'NRC';
  static const String ok = 'OK';
  static const String err = 'ERR';
  static const String evt = 'EVT';
  static const String pong = 'PONG';
}

const Set<String> _serverVerbs = <String>{
  Verb.ready,
  Verb.rsp,
  Verb.nrc,
  Verb.ok,
  Verb.err,
  Verb.evt,
  Verb.pong,
};

/// Raised when a wire-protocol line is malformed or violates grammar.
///
/// A subclass of [FormatException] so callers can use
/// `throwsFormatException` / generic format-error handling.
class ProtocolError extends FormatException {
  ProtocolError(super.message);

  @override
  String toString() => 'ProtocolError: $message';
}

/// Encode bytes as uppercase, space-separated hex (no `0x`).
String bytesToHex(List<int> data) {
  return data
      .map((b) => b.toRadixString(16).toUpperCase().padLeft(2, '0'))
      .join(' ');
}

/// Decode space-separated hex bytes (e.g. `"22 F1 90"`) to a byte list.
///
/// Strict: each token must be exactly two hex digits. Throws
/// [ProtocolError] on malformed input (odd-length tokens, non-hex
/// characters, `0x` prefixes, etc.). Empty input (or whitespace-only)
/// yields `[]`.
List<int> hexToBytes(String s) {
  final tokens = s.trim().isEmpty ? <String>[] : s.trim().split(RegExp(r'\s+'));
  final out = <int>[];
  final hexDigits = RegExp(r'^[0-9a-fA-F]{2}$');
  for (final tok in tokens) {
    if (!hexDigits.hasMatch(tok)) {
      throw ProtocolError('invalid hex byte: $tok');
    }
    out.add(int.parse(tok, radix: 16));
  }
  return out;
}

String _hex2(int v) => v.toRadixString(16).toUpperCase().padLeft(2, '0');

// ---------------------------------------------------------------------------
// Command encoders (client -> server)
// ---------------------------------------------------------------------------

/// `<seq> HELLO proto=1`
String encodeHello(int seq) => '$seq ${Verb.hello} proto=$kProto';

/// `<seq> SESSION <session_hex>`
String encodeSession(int seq, int session) =>
    '$seq ${Verb.session} ${_hex2(session)}';

/// `<seq> READDTC [mask_hex]` -- default mask `FF` per docs/03 §1.2.
String encodeReadDtc(int seq, {int mask = 0xFF}) =>
    '$seq ${Verb.readDtc} ${_hex2(mask)}';

/// `<seq> CLEARDTC`
String encodeClearDtc(int seq) => '$seq ${Verb.clearDtc}';

/// `<seq> SECURITY <level_hex>`
String encodeSecurity(int seq, int level) =>
    '$seq ${Verb.security} ${_hex2(level)}';

/// `<seq> TP START`
String encodeTpStart(int seq) => '$seq ${Verb.tp} START';

/// `<seq> TP STOP`
String encodeTpStop(int seq) => '$seq ${Verb.tp} STOP';

/// `<seq> RAW <byte> <byte> ...`
String encodeRaw(int seq, List<int> data) {
  if (data.isEmpty) return '$seq ${Verb.raw}';
  return '$seq ${Verb.raw} ${bytesToHex(data)}';
}

/// `<seq> PING`
String encodePing(int seq) => '$seq ${Verb.ping}';

/// `<seq> BYE`
String encodeBye(int seq) => '$seq ${Verb.bye}';

// ---------------------------------------------------------------------------
// Response parsing (server -> client)
// ---------------------------------------------------------------------------

/// A server -> client response line.
///
/// Only the fields relevant to [verb] are populated; the rest stay `null`
/// (or empty for [evtArgs]). Mirrors `protocol.wire.Response`.
class Response {
  Response({
    required this.seq,
    required this.verb,
    this.proto,
    this.tool,
    this.transport,
    this.data,
    this.sid,
    this.nrc,
    this.okKind,
    this.level,
    this.errCode,
    this.errText,
    this.evtName,
    this.evtArgs = const <String>[],
  });

  final int seq;
  final String verb;

  // READY
  final int? proto;
  final String? tool;
  final String? transport; // 'A' | 'B'

  // RSP
  final List<int>? data;

  // NRC
  final int? sid;
  final int? nrc;

  // OK
  final String? okKind; // 'TP' | 'SEC'
  final int? level;

  // ERR
  final int? errCode;
  final String? errText;

  // EVT
  final String? evtName;
  final List<String> evtArgs;
}

/// Split a line into `(seq, verb, restTokens)`.
///
/// Throws [ProtocolError] if the line is too long, empty, missing a verb,
/// or has a malformed (non-numeric / negative) seq.
(int, String, List<String>) _splitLine(String line) {
  if (line.length > kMaxLine) {
    throw ProtocolError('line exceeds kMaxLine');
  }
  final stripped = line.trim();
  final tokens = stripped.split(RegExp(r'\s+'));
  if (tokens.length < 2 || (tokens.length == 1 && tokens[0].isEmpty)) {
    throw ProtocolError('malformed line (need at least SEQ and VERB): $line');
  }

  final seqTok = tokens[0];
  final verbTok = tokens[1];
  final rest = tokens.sublist(2);

  final seq = int.tryParse(seqTok);
  if (seq == null || seq < 0) {
    throw ProtocolError('malformed seq: $line');
  }

  return (seq, verbTok.toUpperCase(), rest);
}

/// Parse a server -> client response line (without trailing `\n`).
///
/// Throws [ProtocolError] on malformed input. Tolerant of extra whitespace,
/// strict on grammar per verb.
Response parseResponse(String line) {
  final (seq, verb, rest) = _splitLine(line);

  if (!_serverVerbs.contains(verb)) {
    throw ProtocolError('not a server verb: $verb');
  }

  switch (verb) {
    case Verb.ready:
      final kv = <String, String>{};
      for (final tok in rest) {
        final idx = tok.indexOf('=');
        if (idx < 0) {
          throw ProtocolError('malformed READY arg: $tok');
        }
        kv[tok.substring(0, idx)] = tok.substring(idx + 1);
      }
      if (!kv.containsKey('proto') ||
          !kv.containsKey('tool') ||
          !kv.containsKey('transport')) {
        throw ProtocolError('missing READY field: $line');
      }
      final proto = int.tryParse(kv['proto']!);
      if (proto == null) {
        throw ProtocolError('bad READY proto: ${kv['proto']}');
      }
      final transport = kv['transport']!;
      if (transport != 'A' && transport != 'B') {
        throw ProtocolError('invalid READY transport: $transport');
      }
      return Response(
        seq: seq,
        verb: verb,
        proto: proto,
        tool: kv['tool'],
        transport: transport,
      );

    case Verb.rsp:
      final data = hexToBytes(rest.join(' '));
      return Response(seq: seq, verb: verb, data: data);

    case Verb.nrc:
      if (rest.length != 2) {
        throw ProtocolError('NRC requires exactly 2 args, got $rest');
      }
      final sid = int.tryParse(rest[0], radix: 16);
      final nrcVal = int.tryParse(rest[1], radix: 16);
      if (sid == null || nrcVal == null) {
        throw ProtocolError('bad NRC hex args: $rest');
      }
      return Response(seq: seq, verb: verb, sid: sid, nrc: nrcVal);

    case Verb.ok:
      if (rest.isEmpty) {
        throw ProtocolError('OK requires at least one arg');
      }
      final what = rest[0].toUpperCase();
      if (what == 'TP') {
        if (rest.length != 1) {
          throw ProtocolError('OK TP takes no extra args, got $rest');
        }
        return Response(seq: seq, verb: verb, okKind: 'TP');
      }
      if (what == 'SEC') {
        if (rest.length != 2) {
          throw ProtocolError('OK SEC requires a level arg, got $rest');
        }
        final level = int.tryParse(rest[1], radix: 16);
        if (level == null) {
          throw ProtocolError('bad OK SEC level: ${rest[1]}');
        }
        return Response(seq: seq, verb: verb, okKind: 'SEC', level: level);
      }
      throw ProtocolError('unknown OK kind: ${rest[0]}');

    case Verb.err:
      if (rest.length < 2) {
        throw ProtocolError('ERR requires code and text, got $rest');
      }
      final code = int.tryParse(rest[0]);
      if (code == null) {
        throw ProtocolError('bad ERR code: ${rest[0]}');
      }
      return Response(
          seq: seq,
          verb: verb,
          errCode: code,
          errText: rest.sublist(1).join(' '));

    case Verb.evt:
      if (rest.isEmpty) {
        throw ProtocolError('EVT requires a name');
      }
      return Response(
          seq: seq, verb: verb, evtName: rest[0], evtArgs: rest.sublist(1));

    case Verb.pong:
      if (rest.isNotEmpty) {
        throw ProtocolError('PONG takes no args, got $rest');
      }
      return Response(seq: seq, verb: verb);

    default:
      throw ProtocolError('cannot parse unknown response verb: $verb');
  }
}
