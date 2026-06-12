// Correlation id allocator for the proto=1 wire protocol.
//
// Mirrors `protocol/wire.py`'s `SeqAllocator`. `seq=0` is reserved for
// unsolicited/async messages (docs/03-TECHNICAL-DETAIL.md §1.1), so
// allocation starts at 1.

/// Monotonic per-connection sequence id allocator.
class SeqAllocator {
  int _next = 1;

  /// Returns the next correlation id, starting at 1 and incrementing by 1
  /// on each call.
  int next() {
    final seq = _next;
    _next += 1;
    return seq;
  }
}
