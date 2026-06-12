// Tests for lib/protocol/seq.dart -- correlation id allocator.
// Mirrors protocol/wire.py's SeqAllocator (seq=0 reserved for unsolicited
// per docs/03 §1.1, allocation starts at 1).

import 'package:flexdiag_app/protocol/seq.dart';
import 'package:test/test.dart';

void main() {
  group('SeqAllocator', () {
    test('starts at 1 and increments monotonically', () {
      final alloc = SeqAllocator();
      expect(alloc.next(), 1);
      expect(alloc.next(), 2);
      expect(alloc.next(), 3);
    });

    test('separate allocators are independent', () {
      final a = SeqAllocator();
      final b = SeqAllocator();
      expect(a.next(), 1);
      expect(a.next(), 2);
      expect(b.next(), 1);
    });
  });
}
