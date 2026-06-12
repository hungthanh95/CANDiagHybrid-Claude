"""``.flex`` script runner.

A ``.flex`` file is one REPL command per line:

- Blank lines and lines starting with ``#`` are ignored.
- A line starting with ``?`` means "negative response expected" -- the
  leading ``?`` is stripped before the command is run, and the run is
  considered a *pass* for that line if the server responds with ``NRC`` or
  ``ERR`` (an explicit negative response). If the server instead responds
  positively (``RSP``/``OK``/``PONG``/``READY``), that line fails.
- Any other line is run as if typed into the REPL and must produce a
  positive/non-error response (``RSP``/``OK``/``PONG``/``READY``) or no
  response at all (local commands such as ``connect``/``trace``). ``NRC``
  or ``ERR`` on such a line is a failure.

Execution is fail-fast: the first unexpected failure stops the script.
Exit code ``0`` on full pass, ``1`` on any unexpected failure.
"""

from __future__ import annotations

import asyncio
import logging

from protocol.wire import Verb
from terminal.repl import Repl
from terminal.transport_tcp import TransportError

logger = logging.getLogger(__name__)

_NEGATIVE_VERBS = {Verb.NRC.value, Verb.ERR.value}


def _is_negative(response_verb: str) -> bool:
    return response_verb in _NEGATIVE_VERBS


async def run_script(path: str) -> int:
    """Run the ``.flex`` script at ``path``. Returns the process exit code."""
    repl = Repl()
    exit_code = 0

    try:
        with open(path, encoding="utf-8") as f:
            lines = f.readlines()
    except OSError as exc:
        print(f"cannot read script {path!r}: {exc}")
        return 1

    for lineno, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        expect_negative = line.startswith("?")
        if expect_negative:
            line = line[1:].strip()

        print(f"[{lineno}] {line}")
        try:
            resp = await repl.run_command(line)
        except EOFError:
            break
        except TransportError as exc:
            print(f"[{lineno}] TRANSPORT ERROR: {exc}")
            exit_code = 1
            break

        if resp is None:
            # Local command (connect/trace/etc.) -- no pass/fail verdict
            # unless it was expected to be negative, which is meaningless
            # for local commands.
            if expect_negative:
                print(f"[{lineno}] FAIL: expected negative response but got none")
                exit_code = 1
                break
            continue

        negative = _is_negative(resp.verb)
        if expect_negative and not negative:
            print(f"[{lineno}] FAIL: expected NRC/ERR, got {resp.verb}")
            exit_code = 1
            break
        if not expect_negative and negative:
            print(f"[{lineno}] FAIL: unexpected {resp.verb}")
            exit_code = 1
            break

    await repl.disconnect()
    return exit_code


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("usage: python -m terminal script <path>")
        return 1
    logging.basicConfig(level=logging.WARNING)
    return asyncio.run(run_script(argv[0]))
