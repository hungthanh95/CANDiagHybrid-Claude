# Security Access capability -- software loopback (Mock ECU)
# Covers: FR Security Access (capability matrix), proto=1 SECURITY verb,
# full seed/key unlock at odd level 01 (docs/03 §1.2, §9).
connect 127.0.0.1 ${PORT}
sec 01
bye
