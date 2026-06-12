# Read DTC capability -- Option B (bridge + FakeVectorCom loopback)
# Covers: FR Read DTC (capability matrix), proto=1 READDTC verb (docs/03 §1.2),
# FR-12 (identical protocol both transports).
connectb 127.0.0.1 ${PORT}
readdtc FF
bye
