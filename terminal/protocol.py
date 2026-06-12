"""Thin re-export of :mod:`protocol.wire` for terminal-local convenience.

Per ``docs/04-RULES-AND-CONVENTIONS.md`` §3.5 ("one protocol parser per
language"), this module does NOT re-implement framing -- it only re-exports
the shared codec so terminal modules can ``from terminal.protocol import
...`` without depth-coupling to ``protocol.wire``'s module path.
"""

from __future__ import annotations

from protocol.wire import (
    MAX_LINE,
    PROTO,
    Command,
    ProtocolError,
    Response,
    SeqAllocator,
    Verb,
    bytes_to_hex,
    hex_to_bytes,
    parse_command,
    parse_response,
)

__all__ = [
    "MAX_LINE",
    "PROTO",
    "Command",
    "ProtocolError",
    "Response",
    "SeqAllocator",
    "Verb",
    "bytes_to_hex",
    "hex_to_bytes",
    "parse_command",
    "parse_response",
]
