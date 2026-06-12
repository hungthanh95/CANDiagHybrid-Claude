"""CLI entry point.

- ``python -m terminal`` opens the interactive REPL.
- ``python -m terminal script <path>`` runs a ``.flex`` script and exits
  with its exit code.
"""

from __future__ import annotations

import sys

from terminal.repl import main as repl_main
from terminal.script import main as script_main


def main() -> int:
    args = sys.argv[1:]
    if args and args[0] == "script":
        return script_main(args[1:])
    repl_main()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
