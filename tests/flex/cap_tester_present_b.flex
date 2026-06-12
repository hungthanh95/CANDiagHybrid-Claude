# Tester Present capability -- Option B (bridge + FakeVectorCom loopback)
# Covers: FR-4 Tester Present (capability matrix), proto=1 TP START/STOP
# (docs/03 §1.2).
connectb 127.0.0.1 ${PORT}
tp on
tp off
bye
