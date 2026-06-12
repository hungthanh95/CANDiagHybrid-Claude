"""CLI entry point.

- ``python -m terminal`` opens the interactive REPL.
- ``python -m terminal script <path>`` runs a ``.flex`` script and exits
  with its exit code.
- ``python -m terminal [--transport A|B] [--host HOST] [--port PORT]
  [--url ws://HOST:PORT]`` opens the interactive REPL and automatically
  connects first (docs/05 §7.1/§7.2):

  - ``--transport A`` (default) + ``--host``/``--port`` (default
    ``127.0.0.1``/``9000``) -> runs ``connect <host> <port>`` (Option A,
    TCP) before the interactive loop.
  - ``--transport B`` + ``--url ws://HOST:PORT`` or ``--host``/``--port``
    (default ``127.0.0.1``/``8770``) -> runs ``connectb <host> <port>``
    (Option B, WebSocket bridge) before the interactive loop.

  If none of ``--transport``/``--host``/``--port``/``--url`` are given, the
  REPL opens with no connection (unchanged behaviour) -- the user types
  ``connect``/``connectb`` manually.
"""

from __future__ import annotations

import argparse
import sys
from urllib.parse import urlsplit

from terminal.repl import main as repl_main
from terminal.script import main as script_main


def _parse_url(url: str) -> tuple[str, int]:
    """Parse ``ws://host:port`` (or ``host:port``) into ``(host, port)``."""
    parsed = urlsplit(url if "//" in url else f"//{url}")
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port
    if port is None:
        raise ValueError(f"--url must include a port, e.g. ws://127.0.0.1:8770 (got: {url!r})")
    return host, port


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="terminal", description="FlexDiag terminal client (proto=1)"
    )
    parser.add_argument(
        "--transport",
        choices=["A", "B"],
        default=None,
        help="A=TCP (CAPL TCP server, default), B=WebSocket (Option B bridge)",
    )
    parser.add_argument("--host", default=None, help="server host (default: 127.0.0.1)")
    parser.add_argument(
        "--port", type=int, default=None, help="server port (default: 9000 for A, 8770 for B)"
    )
    parser.add_argument(
        "--url",
        default=None,
        help="Option B only: ws://HOST:PORT, alternative to --host/--port",
    )
    return parser


def main() -> int:
    args = sys.argv[1:]
    if args and args[0] == "script":
        return script_main(args[1:])

    parser = _build_parser()
    ns = parser.parse_args(args)

    if ns.transport is None and ns.host is None and ns.port is None and ns.url is None:
        # Unchanged behaviour: bare interactive REPL.
        repl_main()
        return 0

    transport = ns.transport or "A"

    if transport == "B":
        if ns.url is not None:
            host, port = _parse_url(ns.url)
        else:
            host = ns.host or "127.0.0.1"
            port = ns.port if ns.port is not None else 8770
        initial_command = f"connectb {host} {port}"
    else:
        if ns.url is not None:
            print("--url is only valid with --transport B", file=sys.stderr)
            return 2
        host = ns.host or "127.0.0.1"
        port = ns.port if ns.port is not None else 9000
        initial_command = f"connect {host} {port}"

    repl_main(initial_command)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
