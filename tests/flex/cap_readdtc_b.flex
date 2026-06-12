# Read DTC capability -- Option B (bridge + FakeVectorCom loopback)
# Covers: FR-1/FR-2 Read DTC (capability matrix), proto=1 READDTC verb (docs/03 §1.2).
connectb 127.0.0.1 ${PORT}
readdtc FF
bye
