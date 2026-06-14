# FlexDiag — Project Status

**Maintained by:** `gatekeeper` (Opus) · **Updated:** `2026-06-14` (bridge robustness slice landed: VectorCom auto-start-measurement on connect + cmd_timeout watchdog synthesizing STATUS_ERR_TIMEOUT → `ERR <seq> 504 ecu_timeout` so a hung/absent ECU response no longer hangs the WS client; FakeVectorCom mirrors with a short default for tests. No protocol/sysvar/security change — STATUS_ERR_TIMEOUT was already in docs/03 §2, now produced. 118 tests (113+5), ruff/black clean; software-loopback only. No capability-matrix delta. Earlier 2026-06-13: §3 traceability-accuracy correction — no code change: recorded existing-test coverage for FR-1/3/4/5/6, added rows FR-19/21/24 (✅ mock) + FR-25/26/NFR-7/NFR-10 (🟡 implemented, not formally tested); §3 ✅-convention note added; §2 capability matrix unchanged. Earlier same day: M6 client-resilience slice landed → **M6 In progress, NOT Done**: bounded auto-reconnect (FR-16) on terminal + Flutter, Flutter per-request timeout (NFR-5), NRC-name display — verified vs Mock ECU / Flutter FakeAsync only; FR-16 ⬜→✅. Two M6 DoD items remain human-gated and were NOT attempted: both-tools CANoe+CANalyzer cross-check (CLAUDE.md §3.6) and fresh-machine docs/05 repro (RUNBOOK §4). Earlier: M5 UI slice In progress (FR-17 🟡); PR #7: 2-node agents; PR #5: Option A removed; M3 mock-verified, Vector bring-up pending)

> Single source of truth for project state. Do not mark anything ✅ without a tester-confirmed result on Option B. Legend: ✅ pass · 🟡 partial · ⬜ not yet · ❌ failing.

---

## 1. Milestone board (M0–M6)

| Milestone | Definition of done | Status |
|-----------|--------------------|--------|
| **M0** Protocol frozen | Wire protocol + sysvar layout signed off | ✅ Done — protocol frozen at proto=1, sysvar layout frozen (reviewer-approved) |
| **M1** Software loopback | Terminal ⇄ Mock ECU over plain TCP, all 5 capabilities | ✅ Done — Mock ECU + terminal on software TCP loopback; 87 tests; all 5 capabilities verified; ruff + black clean |
| **M2** Option A live | ❌ **Removed** — Option A parked (R1); operator chose Option B as the sole transport on 2026-06-12. |
| **M3** Option B live | Terminal ⇄ bridge ⇄ COM/sysvar ⇄ Vector | 🟡 In progress — `flexdiag_sysvar.can` + `bridge/` code-complete (reviewer-approved via commit `b1ba857`), all 5 capabilities verified on mock loopback (109 tests passing after Option A removal), real Vector/COM bring-up ⬜ pending |
| **M4** Transport switch | ❌ **Removed** — single transport, no runtime switch. |
| **M5** Flutter parity | Flutter does all 4 capabilities on Option B | 🟡 **In progress** — un-deferred by operator override (2026-06-12), supersedes CLAUDE.md §1a. Foundation slice (proto=1 codec, DTC/NRC codecs, `Transport`/`WsTransport`, `DiagService`) + **UI slice** now landed: `flutter_app/` is a Flutter app (Linux desktop target) with `AppState` (ChangeNotifier), `LoggingTransport` decorator, and 8 screens (connect/session/read-DTC/clear-DTC/security/tester-present/log) for all v1 capabilities, wired only through `AppState`/`DiagService`/`Transport`. 108 widget+unit tests green vs fakes; `flutter analyze`/`dart format` clean. **Not yet ✅:** a human-gated `flutter run` on Linux desktop against `bridge --fake` / Mock ECU is headless-impossible in CI and remains an operator manual step (RUNBOOK §4). No CANoe/CANalyzer license → mock loopback is the verification target (same topology as M1/M3) |
| **M6** Release v1 | Hardened, documented, reproducible setup | 🟡 **In progress** — client-resilience hardening slice landed: bounded auto-reconnect (FR-16) on terminal (`repl.py`) + Flutter (`AppState` + `transport/reconnect_policy.dart`), Flutter `DiagService` per-request timeout (5s → `TransportException`, NFR-5), NRC-name display in `security_screen` + `AppState` log (display-only, codec untouched). All verified vs Mock ECU (software loopback) + Flutter FakeAsync; Python 113 tests + Flutter 115 tests + ruff/black/analyze/format clean. Pre-existing `LoggingTransport` double-logging bug fixed (broadcast-stream caching). **Still outstanding (human-gated, NOT attempted):** (1) both-tools CANoe+CANalyzer cross-check (CLAUDE.md §3.6, docs/00 §6); (2) fresh-machine docs/05 reproducibility check (RUNBOOK §4). No CANoe/CANalyzer license → mock loopback is the verification target |

---

## 2. Capability matrix

Cells show current verified state. A capability is "done" only when Option B is ✅.¹

| Capability | Option B (COM/sysvar) | CANoe | CANalyzer | Mock ECU |
|------------|:--:|:--:|:--:|:--:|
| Read DTC (`0x19 02`) | ⬜ | ⬜ | ⬜ | ✅ |
| Tester Present (`0x3E`) | ⬜ | ⬜ | ⬜ | ✅ |
| Security Access (`0x27`) | ⬜ | ⬜ | ⬜ | ✅ |
| Session Control (`0x10`) | ⬜ | ⬜ | ⬜ | ✅ |
| Clear DTC (`0x14`) | ⬜ | ⬜ | ⬜ | ✅ |

¹ Option B verified on mock loopback (M3). Real Vector bring-up pending.

---

## 3. Requirement traceability (FR → test → state)

> **State convention (§3 only):** ✅ = **verified on the software/mock loopback** (`bridge --fake` / `FakeVectorCom` / Mock ECU semantics). Real-COM / Vector (CANoe, CANalyzer) verification is tracked **separately** in the §2 capability matrix (those columns stay ⬜ until Vector hardware runs). This is the same convention FR-7/FR-18 have always used. 🟡 = implemented but not formally tested (evidence pointer to code, no asserting test). ⬜ = no test yet.

| FR | Requirement (short) | Covering test(s) | State |
|----|---------------------|------------------|-------|
| FR-1 | Read DTC `19 02` | `test_flex_capabilities_b::test_cap_readdtc_b`, `test_mock_uds` (`19 02` resp) | ✅ (mock loopback) |
| FR-2 | Client-side DTC decode | `test_protocol_dtc` | ✅ |
| FR-3 | Clear DTC `14` | `test_flex_capabilities_b::test_cap_clear_dtc_b`, `test_mock_uds` (`0x14`→`0x54`) | ✅ (mock loopback) |
| FR-4 | Periodic Tester Present | `test_flex_capabilities_b::test_cap_tester_present_b` | ✅ (mock loopback) — covers client/bridge TP START/STOP → OK TP round-trip; the *periodic* `3E 80` emission is the Vector tool's job, fully verifiable only on real Vector (§2) |
| FR-5 | Security seed/key | `test_flex_capabilities_b::test_cap_security_b`, `test_mock_uds::test_security_*`, `test_bridge_negatives` (invalidKey/accessDenied) | ✅ (mock loopback) |
| FR-6 | Session control | `test_flex_capabilities_b::test_cap_session_b`, `test_mock_uds` | ✅ (mock loopback) |
| FR-7 | Raw request | `test_flex_capabilities_b` | ✅ |
| FR-8 | NRC surfaced distinctly | `test_bridge_negatives`, `test_protocol_nrc` | ✅ |
| FR-9 | `0x78` pending handled | `test_bridge_negatives::test_pending_0x78_then_final` | ✅ |
| FR-10 | Option A transport | ❌ Removed (2026-06-12) | ❌ |
| FR-11 | Option B transport | `test_bridge_unit` (incl. `_ensure_measurement_running` start/noop/timeout), `test_bridge_negatives` (incl. `test_command_timeout_yields_err_504`), `test_flex_capabilities_b` | 🟡 |
| FR-12 | Identical protocol both transports | ❌ Removed | ❌ |
| FR-13 | Flutter transport switch | ❌ Removed | ❌ |
| FR-14 | Terminal transport switch | ❌ Removed | ❌ |
| FR-15 | Bridge auto-detect CANoe/CANalyzer | `____` | ⬜ |
| FR-16 | Reconnection | `tests/test_terminal_reconnect.py` (terminal, 4), `flutter_app/test/state/app_state_reconnect_test.dart` (Flutter, 4) | ✅ — bounded exponential-backoff auto-reconnect both clients; in-flight requests fail immediately, exhaustion stays cleanly disconnected (no hang). Mock loopback / FakeAsync verified |
| FR-17 | Flutter feature set | `flutter_app/test/ui/**`, `flutter_app/test/state/app_state_test.dart` (+ foundation codec/transport/service) | 🟡 — UI for all v1 capabilities built and wired through DiagService/Transport; 108 widget+unit tests green vs fakes, analyze clean. Stays 🟡 (not ✅) until a human-gated `flutter run` on Linux desktop vs `bridge --fake` / Mock ECU is eyeballed (headless-impossible in CI, RUNBOOK §4) |
| FR-18 | Terminal feature set | `test_flex_capabilities_b` | ✅ |
| FR-19 | Terminal script-file runner | `test_flex_capabilities_b` (all `cap_*_b` run via `terminal/script.py` `.flex` runner against the bridge) | ✅ (mock loopback) |
| FR-20 | Mock ECU responds to core SIDs | `test_mock_uds` | ✅ |
| FR-21 | Mock ECU configurable DTC table | `test_mock_uds` (`Ecu.dtcs: list[tuple[int,int]]` dataclass field, read back by `0x19 02`) | ✅ |
| FR-22 | Mock seed/key matches DLL | `test_mock_uds::test_security_*` | ✅ |
| FR-23 | Mock NRC injection | `test_mock_uds::test_inject_next_nrc`, `test_server_negatives`, `test_bridge_negatives` | ✅ |
| FR-24 | Software `--fake` loopback mode | `test_bridge_unit`, `test_flex_capabilities_b` (`FakeVectorCom` wrapping `mock_ecu.uds.Ecu`; the loopback nearly every bridge/capability test runs on) | ✅ |
| FR-25 | Logging at each layer | bridge Python `logging`; terminal `trace on` (`repl.py`); Flutter `LoggingTransport` (`app_state.dart`) | 🟡 implemented, no dedicated test asserting timestamp+direction+seq at each layer |
| FR-26 | End-to-end seq-id traceability | SEQ generated client-side, echoed on responses, threaded through bridge/sysvars (docs/03 §1.5) | 🟡 implemented (seq echoed through protocol), no dedicated trace-by-seq test |

| NFR-4 | Byte-accurate encode/decode | `test_bridge_unit` | 🟡 |
| NFR-5 | No hang/crash on transport loss or no-response | `tests/test_terminal_reconnect.py` (per-request-timeout, bounded-exhaust-clean), `flutter_app/test/services/diag_service_test.dart` (3 FakeAsync timeout), `test_bridge_negatives::test_command_timeout_yields_err_504` (bridge cmd_timeout → `ERR 504 ecu_timeout`, peer stays alive) | ✅ — mock/FakeAsync verified |
| NFR-7 | Localhost bind default | `bridge/flexdiag_bridge.py` + `bridge/__main__.py` default `host="127.0.0.1"`; remote bind is explicit `--host` | 🟡 implemented in code, no asserting test |
| NFR-10 | COM serialized on single STA thread | `VectorCom` runs COM on one dedicated STA thread (`CoInitialize`/`PumpWaitingMessages`); async side talks only via queues (docs/03 §4.2) | 🟡 architectural (by construction), not unit-testable / real-COM-unverifiable offline |
| NFR-3 | Latency | — | ⬜ no test yet (perf deferred this pass) |
| NFR-9 | Throughput | — | ⬜ no test yet (perf deferred this pass) |

> §3 ✅ = software/mock-loopback verified; real Vector/COM tracked separately in §2 (those columns stay ⬜ until hardware runs). NFR-4 verified on mock (Option B loopback); real Vector/COM pending. NFR-3/NFR-9 (perf) deferred by operator — no coverage claimed.

---

## 4. Recent changes (newest first)

| Date | PR / commit | Change | Topology | Tool |
|------|-------------|--------|----------|------|
| 2026-06-14 | `feat(bridge)` (this PR) | Bridge robustness slice — `VectorCom.__init__` gains `auto_start_measurement`/`measurement_start_timeout` (calls `app.Measurement.Start()` + polls `Running`, `RuntimeError` on timeout) and `cmd_timeout` watchdog: tracks the one outstanding command and, if `RspTrigger` doesn't change in `cmd_timeout`s, emits `(seq, STATUS_ERR_TIMEOUT, kind, b"")` → existing `encode_response` maps to `ERR <seq> 504 ecu_timeout`, then clears so the next command flows; `FakeVectorCom` mirrors with a short default. No UDS bytes interpreted (bridge stays a pure sysvar mover, CLAUDE.md rules 4/5); no protocol/sysvar/0x27/`flexdiag_core.can` change — STATUS_ERR_TIMEOUT already in docs/03 §2, now produced; docs/03 §4.2 notes added. 118 tests (113+5 new), ruff/black clean. No capability-matrix delta (internal robustness; ERR 504 mapping pre-existed). VectorCom unit-tested via MagicMock COM stubs — real-COM still ⬜ (R2) | software loopback (FakeVectorCom + Mock ECU) | n.a. |
| 2026-06-13 | `docs(status)` | **Traceability-accuracy correction, no code change.** §3 was under-reporting verified coverage: filled in FR-1/3/4/5/6 (were `____`/⬜ → ✅ mock loopback, backed by existing passing `test_flex_capabilities_b` cap tests + `test_mock_uds`); added rows FR-19/21/24 (✅ mock, existing tests), FR-25/26 + NFR-7/NFR-10 (🟡 implemented-not-formally-tested, code pointers), NFR-3/NFR-9 (⬜ perf deferred). Added §3 ✅-convention note (✅ = mock-loopback; real Vector tracked in §2) to prevent recurrence. §2 capability matrix untouched. Verified by full `pytest -q` (113 passed) + spot-check of named test functions before marking ✅ | software loopback (Mock ECU) | n.a. (doc-only) |
| 2026-06-13 | `6dca2dc` + `663426c` | M6 client-resilience slice — bounded exponential-backoff auto-reconnect (FR-16) for terminal (`repl.py` `ReconnectPolicy`) + Flutter (`AppState._reconnectLoop` + `transport/reconnect_policy.dart`); in-flight requests fail immediately with `TransportError`/`TransportException` on drop; Flutter `DiagService` per-request timeout (5s → `TransportException`, NFR-5); NRC-name display wired into `security_screen` + `AppState` log (`NRC <sid> <nrc> (<name>)`, display-only); contained `fix(flutter)` caches `LoggingTransport` broadcast stream (fixes double-logging). proto=1 / docs/03 §1/§2 / `flexdiag_core.can` / 0x27 path all untouched; docs/03 §7.1/§8.1 added. Python 113 + Flutter 115 tests green; ruff/black/analyze/format clean. FR-16 ⬜→✅, NFR-5 ✅. M6 stays In progress (human-gated both-tools + fresh-machine repro NOT attempted) | software loopback (Mock ECU) / Flutter FakeAsync | n.a. (no Vector license) |
| 2026-06-13 | PR #10 / `c399fbe` + `4bcd795` | feat(flutter): M5 UI slice — `flutter_app/` converted to a Flutter app (flutter SDK dep, flutter_lints, Linux desktop scaffold under `linux/`); `AppState` (ChangeNotifier: connection lifecycle, log, per-capability last result, ReadyInfo, SecurityResult Success/Nrc/Err); `LoggingTransport` Transport decorator (DiagService unmodified); 8 screens (connect/session/read-DTC/clear-DTC/security/tester-present/home/log) depending only on AppState/DiagService/Transport; docs/03 §7 layout updated; separate `style(flutter)` commit reconciles dart-format tall-style whitespace on 7 foundation files (no logic). 108 flutter tests + analyze + format clean; no protocol/** or §1/§2 change; no protected areas; FR-17 ⬜→🟡 | software loopback (fakes / Mock ECU semantics) | n.a. (no Vector license) |
| 2026-06-12 | `1029905` | feat(flutter): M5 foundation slice (operator un-deferred M5) — new pure-Dart `flutter_app/`: proto=1 wire codec (`protocol/codec.dart`, mirrors `wire.py`), DTC decode (`codec/dtc.dart`, byte-mirrors `protocol/dtc.py`) + NRC name table (`codec/nrc.dart`), `Transport`/`WsTransport` (Option B, web_socket_channel), `DiagService` (readDtc/clearDtc/session/securityUnlock/testerPresent/raw/ping, NrcException≠ErrException); 76 dart tests + end-to-end smoke vs `bridge --fake`; dart format + analyze clean; docs/03 §7 updated; no protocol/** or §1/§2 changes; no protected areas | software loopback | n.a. (no Vector license) |
| 2026-06-12 | PR #7 / a3157b5 | chore(meta)!: consolidate 5-agent setup (`flexdiag-developer`/`-tester`/`-reviewer`/`-shipper`/`-status`) into 2 nodes — `builder` (Sonnet, impl+tests in TDD loop) and `gatekeeper` (Opus, review+commit+PR+merge+STATUS.md); CLAUDE.md §2/§3.3/§4/§6 rewritten; separation of duties preserved at builder↔gatekeeper boundary; no product-code or behaviour change | n.a. | n.a. |
| 2026-06-12 | PR #5 / 3e1588a | chore!: remove Option A (CAPL TCP node, terminal TCP transport, MockServer, mock_ecu CLI, 5 .flex scripts, 3 test modules; 12 files deleted); operator decision: CAPL TCP/IP API license uncertainty → Option B sole transport; 129→109 tests; protocol/wire `READY` field retained as always-`"B"` (proto=1 unchanged); `flexdiag_core.can` + 0x27 security untouched; M2/M4 marked Removed (numbers preserved); R1 closed; FR-10/12/13/14 marked Removed; reviewer-approved | software loopback | n.a. |
| 2026-06-12 | `c52fedd` | test(bridge): add 42 new tests for Option B (32 unit: `FakeVectorCom` dispatch/NRC/status mapping; 5 negative: 0x78/0x35/0x33/drop/BYE; 5 .flex capability scripts); combined matrix via `cap_matrix.py`; 129/129 passing; ruff+black clean | software loopback | n.a. |
| 2026-06-12 | `a1a9d18` | feat(bridge): add `bridge/` package (`flexdiag_bridge.py` VectorCom + FakeVectorCom mock double, WS server, encode_response RspStatus mapping; `terminal/transport_ws.py` WsTransport; `terminal/repl.py` connectb command; `pyproject.toml` websockets dep); M3 code-complete | software loopback | n.a. |
| 2026-06-12 | `b1ba857` | feat(capl): add `flexdiag_sysvar.can` (Option B CAPL transport node); docs/03 §2 RspStatus enum 0-4 + §3.3 sketch rewritten + "Note on sketch vs implementation"; reviewer-approved (Opus) — flexdiag_core untouched, security ownership correct, OK SEC derivation byte-identical to TCP pattern, proto=1 unchanged | software loopback | n.a. |
| 2026-06-12 | `9dce487` | fix(capl): handle `0x78` pending non-terminally; map ECU timeout to ERR 504; M2 reviewer re-review APPROVE | n.a. | n.a. |
| 2026-06-12 | `7d2cea9` | feat(capl): add `flexdiag_core.can` + `flexdiag_tcp.can` for Option A (M2); docs/03 §3.1/§3.2 updates; M2 reviewer first-pass REQUEST CHANGES | n.a. | n.a. |
| 2026-06-12 | `10b04e1` | M1: Mock ECU + terminal + protocol codec on software TCP loopback; 87 tests (codec, mock UDS, server negatives, .flex regression per capability); ruff+black clean | software loopback | n.a. |
| 2026-06-12 | `____` | M0: froze wire protocol (proto=1) + Diag sysvar layout in docs/03-TECHNICAL-DETAIL.md; added Diag::RspKind sysvar; moved 00/01/02/03/05/STATUS/RUNBOOK into docs/ | — | n.a. |

> Topology = software loopback / virtual CAN / VN1610+real ECU. Tool = CANoe / CANalyzer / n.a.

---

## 5. Open risks & blockers (live)

| # | Risk / blocker | Owner | Status |
|---|----------------|-------|--------|
| R1 | CAPL **TCP/IP API** licensing on operator's CANalyzer (Option A Vector bring-up depended on this) | — | **Closed** — Option A removed 2026-06-12, no longer relevant. |
| R2 | **Option B Vector/COM bring-up:** `flexdiag_sysvar.can` + `bridge/` code-complete + reviewer-approved; real COM/sysvar verification ⬜ pending | — | Active — Option B code approved; mock-loopback parity (all 5 capabilities) verified; real Vector/COM bring-up checklist pending |
| R3 | Seed-key **DLL bitness** must match the Vector process | — | Open |
| R4 | Raw-request / sysvar **CAPL syntax** may differ across tool versions | — | Open — pin reference version |
| R5 | **VN1610 channel** assignment for tool + passive coexistence | — | Open |
| R6 | Mock ECU **key algorithm** drift vs test DLL silently breaks `0x27` test | — | Open |

---

## 6. Next actions

- [x] Freeze wire protocol + sysvar layout → **M0**.
- [x] Build Mock ECU + terminal on software loopback → **M1**.
- [x] **Prioritize M3:** write `flexdiag_sysvar.can` + Python `bridge/` (Option B) → **M3 code-complete + mock verified**.
- [x] Remove Option A (CAPL TCP transport, MockServer, mock_ecu CLI, terminal TCP transport) per operator decision (R1 closed).
- [ ] Run M3 Vector/COM bring-up checklist (docs/05 §8) once an operator can drive `pywin32` / CANoe/CANalyzer.
- [ ] **M5 operator manual step:** `flutter run` the Linux desktop app against `bridge --fake` / Mock ECU and eyeball all v1 capability screens (RUNBOOK §4). Headless-impossible in CI; required before FR-17 → ✅.
