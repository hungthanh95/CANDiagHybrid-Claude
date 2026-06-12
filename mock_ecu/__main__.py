"""CLI entry point: ``python -m mock_ecu --host 127.0.0.1 --port 9000``."""

from __future__ import annotations

import argparse
import logging
import signal
import threading

from mock_ecu.server import MockServer


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="mock_ecu", description="FlexDiag Mock ECU (TCP loopback, proto=1)"
    )
    parser.add_argument("--host", default="127.0.0.1", help="bind address (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=9000, help="bind port (default: 9000)")
    parser.add_argument(
        "--tool",
        default="Mock",
        help="value reported in READY's tool= field (default: Mock)",
    )
    parser.add_argument(
        "--transport",
        default="A",
        choices=["A", "B"],
        help="value reported in READY's transport= field (default: A)",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="enable debug logging")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    server = MockServer(
        host=args.host,
        port=args.port,
        tool_label=args.tool,
        transport_label=args.transport,
    )
    server.start()
    logging.getLogger(__name__).info(
        "Mock ECU listening on %s:%d (proto=1, transport=%s)",
        args.host,
        server.bound_port,
        args.transport,
    )

    stop_evt = threading.Event()

    def _handle_signal(signum: int, _frame: object) -> None:
        del signum
        stop_evt.set()

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    stop_evt.wait()
    server.stop()


if __name__ == "__main__":
    main()
