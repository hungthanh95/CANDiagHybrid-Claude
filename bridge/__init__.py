"""FlexDiag Option B bridge: COM/System-Variable <-> WebSocket.

See ``docs/03-TECHNICAL-DETAIL.md`` §4 for the architecture. The bridge
itself never interprets diagnostic bytes -- it only moves
``Diag::*`` System Variable values to/from a small WebSocket server speaking
the proto=1 wire protocol (``protocol.wire``), shared with Option A.
"""
