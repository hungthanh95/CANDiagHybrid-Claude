"""Mock ECU: UDS responder + TCP-loopback wire-protocol front-end.

For M1 (software loopback) this package stands in for the entire
CAPL+ECU stack; the terminal connects to ``mock_ecu.server.MockServer``
over TCP exactly as it would to a real Option A CAPL TCP transport.
"""
