// Bounded exponential-backoff policy for client-side auto-reconnection
// (FR-16, NFR-5). Mirrors `terminal/repl.py`'s `ReconnectPolicy`.
//
// Pure data + arithmetic -- no I/O, no Transport/AppState dependency, so it
// can be unit-tested in isolation and reused by AppState's reconnect loop.

/// Bounded exponential-backoff policy for auto-reconnection.
///
/// [maxAttempts] caps the number of reconnect attempts after a transport
/// drop (`0` disables auto-reconnect). [baseDelay] is the delay before the
/// first attempt; each subsequent attempt doubles the delay
/// (`baseDelay * 2^k`), capped at [maxDelay].
class ReconnectPolicy {
  const ReconnectPolicy({
    this.maxAttempts = 5,
    this.baseDelay = const Duration(milliseconds: 500),
    this.maxDelay = const Duration(seconds: 10),
  });

  final int maxAttempts;
  final Duration baseDelay;
  final Duration maxDelay;

  /// Backoff delay before reconnect [attempt] (0-indexed), capped at
  /// [maxDelay].
  Duration delayFor(int attempt) {
    final scaled = baseDelay * (1 << attempt);
    return scaled > maxDelay ? maxDelay : scaled;
  }
}
