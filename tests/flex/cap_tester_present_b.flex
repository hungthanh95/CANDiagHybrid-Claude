# Tester Present capability -- Option B (bridge + FakeVectorCom loopback)
# Covers: FR Tester Present (capability matrix), proto=1 TP START/STOP
# (docs/03 §1.2), FR-12 (identical protocol both transports).
connectb 127.0.0.1 ${PORT}
tp on
tp off
bye
