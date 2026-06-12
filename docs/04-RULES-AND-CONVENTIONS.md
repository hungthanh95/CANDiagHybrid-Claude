# Rules & Conventions — FlexDiag

**Document:** Rules & Conventions
**Status:** Draft v1.0

These rules keep the protocol stable and the code portable across CANoe/CANalyzer and tool versions. They are normative: deviations need a note in the relevant doc.

> **Note (2026-06-12):** Option A (CAPL TCP) was removed; Option B (COM + System Variables / WebSocket bridge) is the sole transport. See `docs/STATUS.md` §5 (R1) and `CLAUDE.md` §1a.

---

## 1. Protocol rules (highest priority — everything depends on these)

1. **One protocol, single transport.** Option B (sysvar/WebSocket) MUST expose the documented wire-protocol semantics. No verb or field may be added without a `proto=N` bump (rule 2).
2. **The protocol is frozen at M0.** Changes after M0 require a version bump in the `HELLO`/`READY` handshake (`proto=N`) and updates to both clients and the transport in the same change.
3. **Client builds SIDs; server forwards raw.** At the protocol boundary, request/response payloads are always full UDS frames. The CAPL layer and bridge MUST NOT silently rewrite UDS bytes (the only CAPL-built bytes are the security key-send and tester-present, which are part of documented multi-step flows).
4. **Every terminal command gets exactly one terminal response** (`RSP`/`NRC`/`OK`/`ERR`) carrying the request's `SEQ`. Async notifications use `EVT` at `SEQ=0`.
5. **NRC ≠ ERR.** An ECU negative response is `NRC <sid> <nrc>`. `ERR` is reserved for protocol/tool failures that never reached or never returned from the ECU.
6. **Hex format is fixed:** uppercase, no `0x`, space-separated, MSB-first within a frame. Reject malformed hex with `ERR 422 bad_args`.
7. **Unknown verbs never crash a peer.** Respond `ERR 400 unknown_verb` and keep the connection alive.

---

## 2. CAPL rules

1. **All diagnostic calls live in `flexdiag_core.can`.** The transport node (`flexdiag_sysvar.can`) MUST NOT call `diagSendRequest`, `diagGenerateKeyFromSeed`, or tester-present functions directly — it calls core helpers and implements the `PublishRsp` hook only.
2. **Isolate version-sensitive syntax.** Raw-request construction (`diagRequest ECU1.*`, `diagSetPrimitiveData`, sysvar data get/set) is the most version-fragile part. Keep it in `flexdiag_core.can` (and the thin sysvar accessors) so a tool-version port touches one or two files.
3. **`diagSetTarget("ECU1")` on `on start`** in every transport node — required on CANalyzer and harmless on CANoe. The qualifier `ECU1` MUST match the Basic Diagnostics ECU name exactly.
4. **No CDD assumptions.** Never reference symbolic request/parameter names; only raw bytes. Decoding is the client's job.
5. **Bound every buffer.** Cap response copies at `kMaxLen` (4095). Never index a CAPL array past `elcount`.
6. **Security state is explicit.** The seed→key continuation MUST be driven by a small explicit state (current security seq + level), checked in `PublishRsp`. Do not infer security context from global timing.
7. **Log at the boundary.** Each node writes the inbound command and outbound response to the Write window with the `SEQ`.
8. **Tester present uses the built-in mechanism** (`diagStartTesterPresent`/`diagStopTesterPresent`) — do not hand-roll a `3E` timer.

---

## 3. Python rules (bridge, terminal, mock)

1. **COM is single-threaded.** All COM/sysvar access runs on one dedicated STA thread that calls `CoInitialize` once and `PumpWaitingMessages` in its loop. The asyncio/WebSocket side communicates with it only via queues. Never `Dispatch` or touch a sysvar from the async thread (NFR-10).
2. **Auto-detect tool, fail loudly.** The bridge tries `CANoe.Application` then `CANalyzer.Application` (or an explicit override). If none is reachable, it returns `ERR 503 tool_unavailable` to clients and logs why — it does not retry forever silently.
3. **DLL bitness matches the consumer.** The seed-key DLL is called inside CAPL (Vector process), so the bridge never loads it. If a Python test path ever loads a DLL, its bitness MUST match the Python interpreter; otherwise run it in a matching-bitness subprocess.
4. **Mock key algorithm is documented and matches the test DLL.** The Mock ECU's `test_key` MUST be the same algorithm as the test seed-key DLL (or both reference one documented test algorithm), or the offline security test is meaningless.
5. **One protocol parser per language, shared by clients and mock.** `protocol.py` is the single source for encode/parse in Python; do not re-implement framing per file.
6. **Type and format.** Target Python 3.10+, use type hints, `ruff`/`black` formatting, and `logging` (never bare `print` in library code; the terminal UI may print).
7. **No hidden global state across requests** except the explicitly-modelled session/security/tester-present state.

---

## 4. Flutter / Dart rules

1. **Transport behind an interface.** Screens depend on `DiagService`, never on a concrete `WsTransport`/`Transport` implementation. UI code is unaware of the underlying transport.
2. **Codecs are pure and tested.** DTC/NRC decoding lives in `codec/` as pure functions with unit tests. No I/O in codecs.
3. **All bytes in, all bytes logged.** The raw request/response line is always available in the log view for support.
4. **No business logic in widgets.** Service orchestration (e.g. the single-action security unlock) lives in `services/`, not in button handlers.
5. **Formatting/lints:** `dart format`, `flutter analyze` clean before merge.

---

## 5. Naming conventions

| Thing | Convention | Example |
|-------|------------|---------|
| Protocol verbs | UPPERCASE | `READDTC`, `SECURITY` |
| Sysvars | `Diag::PascalCase` | `Diag::ReqTrigger` |
| CAPL functions | `PascalCase` verbs | `DoReadDtc`, `SecuritySendKey` |
| CAPL files | `flexdiag_<role>.can` | `flexdiag_core.can` |
| Python modules | `snake_case` | `flexdiag_bridge.py` |
| Dart files | `snake_case.dart` | `codec.dart` |
| Diagnostic ECU qualifier | `ECU1` (fixed in v1) | — |
| Default port | WS `8770` | — |
| Default CAN IDs | phys req `0x7E0`, resp `0x7E8` | — |

---

## 6. Configuration rules

1. **Defaults are documented and overridable.** Ports, CAN IDs, addressing mode, P2/P2* timing, tester-present period, and security level all have a single documented default and a single override point.
2. **Addressing/ID changes are config, not code.** Switching 11-bit↔29-bit or changing request/response IDs happens in the diagnostic layer config; no client or protocol change.
3. **The reference tool version is pinned** in the setup guide. CAPL that fails to compile on another version is fixed in `flexdiag_core.can` with a version note.

---

## 7. Git / workflow rules

1. **Conventional commits:** `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:` with a scope, e.g. `feat(capl): add security key-send continuation`.
2. **Protocol changes are atomic:** a single commit/PR updates the spec doc, the transport, and both clients. Never merge a protocol change that lands on only one side.
3. **No secrets in the repo:** real seed-key DLLs, ECU keys, and customer CAN matrices are kept out of version control; only the *test* DLL/algorithm and Mock ECU live in-repo.
4. **Each PR states which topology it was tested on** (software loopback / virtual CAN / VN1610 + real ECU) and on which tool (CANoe/CANalyzer).
5. **Docs travel with code.** Behaviour changes update the relevant `docs/*.md` in the same PR.

---

## 8. Testing rules

1. **Mock-first.** New protocol behaviour is proven against the Mock ECU (software loopback) before touching Vector.
2. **Single transport (Option B).** All capabilities ship on the COM + sysvar bridge; the prior Option A (CAPL TCP) was removed on 2026-06-12 due to CAPL TCP/IP API licensing uncertainty. Release requires passing on CANoe and CANalyzer.
3. **Both tools for release.** Before tagging v1, every capability passes on CANoe and on CANalyzer.
4. **Negative paths are tested,** not just happy paths: at least `0x78` pending, `0x35` invalidKey, `0x33` securityAccessDenied, malformed protocol line, and transport drop mid-request.
5. **Byte-accuracy is verified against a trace** for at least one request per service (NFR-4).

---

## 9. Safety / operational rules

1. **Localhost by default.** The WebSocket bridge binds to `127.0.0.1`. Remote binding is an explicit, documented opt-in and is not part of v1 hardening.
2. **Security access is gated by intent.** The tool only performs `0x27` when the operator explicitly triggers it; no automatic unlocking.
3. **Real keys never logged.** Seeds may be logged for debugging; generated keys MUST NOT be written to persistent logs.
4. **The tool owns the hardware.** Clients never access `vxlapi` directly; the VN1610 is driven only by the measurement (ENV-10).

---

## 10. AI workflow & role assignment

The project is built with AI agents under defined roles. The **executable contract** for those roles lives in `CLAUDE.md` (repo root), which Claude Code loads automatically; the role definitions (with model assignment) live in `.claude/agents/`. This document remains the source of truth for *what the rules are*; `CLAUDE.md` is how agents *execute* them.

1. **Roles and models** (see `CLAUDE.md` §2 and `.claude/agents/`):
   - **Reviewer** (`flexdiag-reviewer`, Opus) — reviews/approves all changes to the protocol, sysvar layout, `flexdiag_core.can`, the `0x27` flow, and ADRs.
   - **Developer** (`flexdiag-developer`, Sonnet) — implements bridge, Mock ECU, terminal, Flutter UI, and CAPL transport nodes.
   - **Tester** (`flexdiag-tester`, Sonnet to author / Haiku to run) — codec unit tests, negative-path tests, regression runs on both transports.
   - **Status** (`flexdiag-status`, Haiku) — maintains `docs/STATUS.md`.
2. **Separation of duty.** The developer role MUST NOT self-approve changes to protected areas (protocol, sysvar layout, `flexdiag_core.can`, security path). The reviewer role approves those before merge.
3. **Protocol changes are atomic and reviewed** (restates §1): spec doc + transport + both clients + `proto=N` bump, in one PR, with reviewer approval.
4. **Status is evidence-based.** A capability reaches ✅ in `docs/STATUS.md` only on a tester-confirmed pass on Option B; otherwise it stays 🟡/⬜.
5. **Docs travel with code** (restates §7): a behaviour change updates the relevant `docs/*.md` and `docs/STATUS.md` in the same PR.
