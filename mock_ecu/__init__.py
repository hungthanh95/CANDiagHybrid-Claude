"""Mock ECU: pure UDS responder state machine.

:class:`mock_ecu.uds.Ecu` implements the UDS request/response state machine
(seed/key security, DTC table, session control, NRC injection) used for
mock-first testing. It has no transport of its own -- Option B's
``bridge --fake`` mode (:class:`bridge.flexdiag_bridge.FakeVectorCom`) wraps
it to provide the same software-loopback testing that the terminal and
``.flex`` scripts drive over the WebSocket bridge.
"""
