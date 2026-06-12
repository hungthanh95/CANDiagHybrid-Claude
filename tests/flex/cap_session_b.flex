# Diagnostic Session Control capability -- Option B (bridge + FakeVectorCom loopback)
# Covers: FR session control (capability matrix), proto=1 SESSION verb
# (docs/03 §1.2), FR-12 (identical protocol both transports).
connectb 127.0.0.1 ${PORT}
session 03
bye
