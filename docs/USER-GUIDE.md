# USER GUIDE — Using FlexDiag

How to **operate** FlexDiag day-to-day: start the transport, drive UDS
diagnostics from the Python terminal, and run scripted capability checks.

This is the *operator* guide. It is distinct from:
- `docs/RUNBOOK.md` — driving the *project* (milestones) with AI agents.
- `docs/05-CANOE-CANALYZER-SETUP.md` — one-time Vector tool + bridge bring-up.
- `docs/03-TECHNICAL-DETAIL.md` — the wire protocol / sysvar contract.

> **Capabilities (v1):** Read DTC · Clear DTC · Diagnostic Session Control ·
> Security Access (seed/key) · Tester Present — plus raw UDS, ping, and a
> `.flex` script runner. Everything runs **offline against a Mock ECU**, or
> **live against CANoe/CANalyzer + VN1610** over the same protocol.

---

## 1. The two run modes

| Mode | Transport backend | Hardware? | Use it for |
|------|-------------------|-----------|------------|
| **Offline (mock)** | `bridge --fake` → `FakeVectorCom` → Mock ECU | none | Learning the tool, scripting, regression, CI |
| **Live (Vector)** | `bridge` → COM/System Variables → CANoe/CANalyzer → VN1610 → ECU | VN1610 + Vector tool + ECU | Real diagnostics |

Both modes speak the **identical** wire protocol (`proto=1`) to the terminal,
so anything you learn or script offline runs unchanged against real hardware.
**Diagnostics live in CAPL** (live) or the Mock ECU (offline); the bridge only
moves bytes — it contains no diagnostic logic.

```
terminal (REPL / .flex)  ──WebSocket (proto=1)──▶  bridge  ──▶ {FakeVectorCom→Mock ECU | COM→Vector→VN1610→ECU}
```

---

## 2. Prerequisites

- Python 3.11+ with the project installed (editable) and dev deps:
  ```
  python -m venv .venv && . .venv/bin/activate
  pip install -e ".[dev]"
  ```
- **Offline mode needs nothing else** — no `pywin32`, no Vector tool.
- **Live mode** additionally needs Windows + `pywin32`, a running CANoe or
  CANalyzer with the `Diag::` sysvar namespace imported, and the seed-key DLL
  attached. See `docs/05-CANOE-CANALYZER-SETUP.md` before using live mode.

---

## 3. Quick start (offline, 60 seconds)

Open **two terminals** from the repo root.

**Terminal 1 — start the bridge (mock backend):**
```
python -m bridge --fake
```
You should see it bind to `127.0.0.1:8770` (the default). Add `-v` for debug
logging.

**Terminal 2 — start the client and auto-connect:**
```
python -m terminal --host 127.0.0.1 --port 8770
```
Then read DTCs:
```
flexdiag> readdtc FF
RSP 59 02 FF 00 12 34 2F 00 56 78 08
  P01234 (status=0x2F)
  P05678 (status=0x08)
flexdiag> quit
```

That's the whole loop: a request verb in, a decoded UDS response out.

---

## 4. Starting the bridge

```
python -m bridge [--host 127.0.0.1] [--port 8770] [--prefer auto|CANoe|CANalyzer] [--fake] [-v]
```

| Flag | Default | Meaning |
|------|---------|---------|
| `--host` | `127.0.0.1` | Bind address. Localhost-only by default; binding to a non-loopback address is an explicit opt-in (not part of v1 hardening). |
| `--port` | `8770` | WebSocket port. |
| `--prefer` | `auto` | Live mode only: which COM server to attach (`auto` tries CANoe then CANalyzer). Ignored with `--fake`. |
| `--fake` | off | Use `FakeVectorCom` (Mock ECU) instead of real COM — **offline mode**. |
| `-v` / `--verbose` | off | Debug-level logging. |

Stop the bridge with `Ctrl-C`.

---

## 5. Starting the terminal

```
python -m terminal [--host HOST] [--port PORT] [--url ws://HOST:PORT]
python -m terminal script <path.flex>
```

- **Bare** `python -m terminal` → opens the REPL with **no** connection; type
  `connectb` yourself.
- **With** `--host`/`--port` *or* `--url ws://HOST:PORT` → opens the REPL and
  runs `connectb` for you first. (`--url` must include a port.)
- **`script <path>`** → runs a `.flex` script non-interactively and exits with
  its status code (see §8).

---

## 6. REPL command reference

Each command maps 1:1 to a wire-protocol verb (plus a few local conveniences).
The client allocates the `seq`, sends the line, waits for the matching
response, and renders it. Unsolicited `READY`/`EVT` banners (seq=0) are printed
but not awaited.

| Command | Wire verb | What it does | Typical response |
|---------|-----------|--------------|------------------|
| `connectb [host] [port]` | — (local) | Connect over WebSocket (Option B). Defaults `127.0.0.1 8770`. | `connected (Option B) to …` |
| `readdtc [mask_hex]` | `READDTC` | Read DTCs by status mask (`0x19 02`). Mask defaults to `FF`. | `RSP 59 02 …` (decoded) |
| `cleardtc` | `CLEARDTC` | Clear all DTCs (`0x14 FF FF FF`). | `RSP 54` |
| `session <hex>` | `SESSION` | Diagnostic Session Control (`0x10 <sub>`). | `RSP 50 <sub> …` |
| `sec <level_hex>` | `SECURITY` | Security Access seed→key unlock at an odd level. Alias: `security`. | `OK SEC <level>` |
| `tp on` / `tp off` | `TP START`/`STOP` | Start/stop periodic Tester Present. | `OK TP` |
| `raw <hex …>` | `RAW` | Send arbitrary UDS bytes, e.g. `raw 22 F1 90`. | `RSP …` or `NRC …` |
| `ping` | `PING` | Liveness check. | `PONG` |
| `bye` | `BYE` | Graceful server-side close (no reply), then disconnect. | — |
| `trace on` / `trace off` | — (local) | Toggle line-level wire logging to stderr (`-> …` / `<- …`). | `trace on/off` |
| `quit` / `exit` | — (local) | Leave the REPL. | — |

**Response rendering:**
- `RSP <bytes>` — positive response (raw UDS hex). After `readdtc`, each DTC is
  additionally decoded, e.g. `P01234 (status=0x2F)`.
- `NRC <sid> <code> (<name>)` — negative response, name from the NRC table
  (e.g. `NRC 27 35 (invalidKey)`).
- `OK TP` / `OK SEC <level>` — capability acknowledgements.
- `ERR <code> <text>` — bridge/transport-level error (not a UDS NRC).
- `PONG` — ping reply.

---

## 7. Worked examples (offline against the Mock ECU)

The Mock ECU ships a two-DTC table and the **v1 test seed-key algorithm**
(`key[i] = seed[i] ^ 0x5A`). Expected outputs below are exact.

**Read DTC (all statuses):**
```
flexdiag> readdtc FF
RSP 59 02 FF 00 12 34 2F 00 56 78 08
  P01234 (status=0x2F)
  P05678 (status=0x08)
```
Filtering by mask returns a subset, e.g. `readdtc 20` matches only the first
DTC; `readdtc 40` matches none (`(no DTCs)`).

**Clear DTC:**
```
flexdiag> cleardtc
RSP 54
```

**Session control (extended = 0x03):**
```
flexdiag> session 03
RSP 50 03 00 32 01 F4
```

**Security Access (odd level 01, full seed→key unlock):**
```
flexdiag> sec 01
OK SEC 01
```
The single `sec` command performs the full two-step exchange (requestSeed →
computed sendKey) and reports the unlock. A wrong key surfaces as
`NRC 27 35 (invalidKey)`.

**Tester Present:**
```
flexdiag> tp on
OK TP
flexdiag> tp off
OK TP
```

**Raw UDS (read VIN data identifier; unsupported on the mock):**
```
flexdiag> raw 22 F1 90
NRC 22 11 (serviceNotSupported)
```

> Live mode is identical at the terminal — point the bridge at the Vector tool
> (drop `--fake`) and run the same commands. Real responses depend on your ECU
> and CAN matrix. **Security against a real ECU is a human-gated step** — see
> `docs/RUNBOOK.md` §4.

---

## 8. Scripting with `.flex`

A `.flex` file is one REPL command per line. Run it with:
```
python -m terminal script path/to/file.flex
```

Rules:
- Blank lines and `#` comments are ignored.
- `${PORT}` is **not** auto-substituted by the runner — supply a literal port,
  or use the substitution that `tests/cap_matrix.py` performs when it renders
  the bundled `tests/flex/*.flex` templates.
- A normal line **must** get a positive/non-error response (`RSP`/`OK`/`PONG`/
  `READY`) or be a local command (`connectb`/`trace`).
- A line prefixed with `?` **expects a negative** response — it passes only if
  the server replies `NRC` or `ERR`. (Use this to assert error paths.)
- Execution is **fail-fast**: the first unexpected result stops the script.
- Exit code: `0` = full pass, `1` = any unexpected failure.

Example (`cap_security_b.flex`):
```
connectb 127.0.0.1 8770
sec 01
bye
```

The five bundled capability scripts live in `tests/flex/`. To print the
capability pass/fail matrix (each script run against a fresh mock bridge):
```
python -m tests.cap_matrix
```

---

## 9. Reliability behaviours

- **Auto-reconnect (FR-16):** if the WebSocket drops, any in-flight request
  fails immediately (no hang), then the REPL retries with bounded exponential
  backoff (default 5 attempts, 0.5 s → 10 s cap). On success the session
  resumes transparently; on exhaustion it stays cleanly disconnected.
- **Per-request timeout:** each request waits up to 5 s for its matching
  response, then raises a transport error rather than hanging.
- **Response correlation:** responses are matched by `seq`; unsolicited
  `seq=0` banners (`READY`, `EVT`) never satisfy a pending request.

---

## 10. Troubleshooting

| Symptom | Likely cause / fix |
|---------|--------------------|
| `not connected (use: connectb …)` | No active connection — run `connectb` or start the terminal with `--host`/`--url`. |
| `transport error: timed out waiting for response` | Bridge not running, wrong port, or the backend stalled. Check the bridge terminal; verify host/port. |
| Connection refused on connect | Bridge not started, or bound to a different host/port than the terminal targets. |
| All capabilities `NRC … serviceNotSupported` in live mode | Vector Basic Diagnostics / `ECU1` IDs not configured — see `docs/05` §4. |
| Security never unlocks live | Seed-key DLL not attached, or DLL bitness ≠ tool process bitness (`docs/05`, `docs/RUNBOOK.md` §4). |
| Want to see the raw wire | `trace on` — prints `-> …` / `<- …` to stderr. Or start the bridge with `-v`. |

---

## 11. Pointers

| Need | File |
|------|------|
| All testable use cases / manual test plan | `docs/TEST-CASES.md` |
| Wire protocol, sysvars, codecs | `docs/03-TECHNICAL-DETAIL.md` |
| Vector tool setup + bring-up | `docs/05-CANOE-CANALYZER-SETUP.md` |
| Live project status / capability matrix | `docs/STATUS.md` |
| Driving the project with AI agents | `docs/RUNBOOK.md` |
