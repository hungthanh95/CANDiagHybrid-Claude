# Read DTC capability -- software loopback (Mock ECU)
# Covers: FR Read DTC (capability matrix), proto=1 READDTC verb (docs/03 §1.2).
connect 127.0.0.1 ${PORT}
readdtc FF
bye
