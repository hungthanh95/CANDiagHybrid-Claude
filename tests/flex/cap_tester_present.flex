# Tester Present capability -- software loopback (Mock ECU)
# Covers: FR Tester Present (capability matrix), proto=1 TP START/STOP (docs/03 §1.2).
connect 127.0.0.1 ${PORT}
tp on
tp off
bye
