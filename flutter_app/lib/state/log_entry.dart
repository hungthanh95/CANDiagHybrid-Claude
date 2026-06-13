// Log entry model for the app-level log view (docs/03-TECHNICAL-DETAIL.md
// §7). Pure data -- no protocol logic.

/// Direction/kind of a [LogEntry], used by the log view to style each line.
///
/// `nrc` (ECU negative response, `NRC <sid> <nrc>`) and `err`
/// (protocol/tool error, `ERR <code> <text>`) are distinct kinds -- "NRC ≠
/// ERR" (CLAUDE.md rule, docs/03 §1.3) -- so the UI can render them
/// differently rather than collapsing both into a generic "error".
enum LogDirection {
  /// A protocol line sent to the server.
  sent,

  /// A protocol line received from the server.
  recv,

  /// An informational/status message generated locally (e.g. "connected").
  info,

  /// An ECU negative response (`NRC <sid> <nrc>`).
  nrc,

  /// A protocol/tool error (`ERR <code> <text>`).
  err,
}

/// One entry in the running log of sent/received protocol lines and status
/// messages.
class LogEntry {
  LogEntry({required this.direction, required this.text, DateTime? at})
    : at = at ?? DateTime.now();

  final LogDirection direction;
  final String text;
  final DateTime at;
}
