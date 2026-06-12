# Clear DTC capability -- Option B (bridge + FakeVectorCom loopback)
# Covers: FR clear DTC (capability matrix), proto=1 CLEARDTC verb
# (docs/03 §1.2), FR-12 (identical protocol both transports).
connectb 127.0.0.1 ${PORT}
cleardtc
bye
