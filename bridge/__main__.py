"""CLI entry point: ``python -m bridge [--host 127.0.0.1] [--port 8770] [--prefer auto] [--fake]``.

Option B bridge (docs/03 §4): COM/System-Variable <-> WebSocket. ``--fake``
runs :class:`bridge.flexdiag_bridge.FakeVectorCom` (mock-first, no
COM/pywin32 required); otherwise :class:`bridge.flexdiag_bridge.VectorCom`
connects to CANoe/CANalyzer.
"""

from __future__ import annotations

import argparse
import asyncio
import logging

from bridge.flexdiag_bridge import FakeVectorCom, VectorCom, serve


async def _run(host: str, port: int, prefer: str, fake: bool) -> None:
    vec: FakeVectorCom | VectorCom
    if fake:
        vec = FakeVectorCom()
    else:
        vec = VectorCom(prefer=prefer)

    vec.start()
    try:
        await serve(host, port, vec)
    finally:
        vec.stop()


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="bridge", description="FlexDiag Option B bridge (COM/sysvar <-> WebSocket, proto=1)"
    )
    parser.add_argument("--host", default="127.0.0.1", help="bind address (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8770, help="bind port (default: 8770)")
    parser.add_argument(
        "--prefer",
        default="auto",
        choices=["auto", "CANoe", "CANalyzer"],
        help="preferred COM server (default: auto -- tries CANoe then CANalyzer)",
    )
    parser.add_argument(
        "--fake",
        action="store_true",
        help="use FakeVectorCom (mock_ecu.uds.Ecu) instead of real COM (mock-first/no pywin32)",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="enable debug logging")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    try:
        asyncio.run(_run(args.host, args.port, args.prefer, args.fake))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
