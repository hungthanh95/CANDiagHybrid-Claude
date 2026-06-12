# Security Access capability -- Option B (bridge + FakeVectorCom loopback)
# Covers: FR-5 Security Access (capability matrix), proto=1 SECURITY verb,
# full seed/key unlock at odd level 01 (docs/03 §1.2, §9).
connectb 127.0.0.1 ${PORT}
sec 01
bye
