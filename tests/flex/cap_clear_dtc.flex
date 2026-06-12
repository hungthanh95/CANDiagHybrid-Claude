# Clear DTC capability -- software loopback (Mock ECU)
# Covers: FR clear DTC (capability matrix), proto=1 CLEARDTC verb (docs/03 §1.2).
connect 127.0.0.1 ${PORT}
cleardtc
bye
