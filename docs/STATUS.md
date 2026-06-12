# FlexDiag — Project Status

**Maintained by:** `flexdiag-status` (Haiku) · **Updated:** `2026-06-12` (PR #5 merged: Option A removed, Option B is sole transport; M3 mock-verified, Vector bring-up pending)

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
| **M5** Flutter parity | Flutter does all 4 capabilities on Option B | ⬜ **Deferred** — Python terminal is v1 test client; see CLAUDE.md §1a |
| **M6** Release v1 | Hardened, documented, reproducible setup | ⬜ Not started |

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

| FR | Requirement (short) | Covering test(s) | State |
|----|---------------------|------------------|-------|
| FR-1 | Read DTC `19 02` | `____` | ⬜ |
| FR-2 | Client-side DTC decode | `test_protocol_dtc` | ✅ |
| FR-3 | Clear DTC `14` | `____` | ⬜ |
| FR-4 | Periodic Tester Present | `____` | ⬜ |
| FR-5 | Security seed/key | `____` | ⬜ |
| FR-6 | Session control | `____` | ⬜ |
| FR-7 | Raw request | `test_flex_capabilities_b` | ✅ |
| FR-8 | NRC surfaced distinctly | `test_bridge_negatives`, `test_protocol_nrc` | ✅ |
| FR-9 | `0x78` pending handled | `test_bridge_negatives::test_pending_0x78_then_final` | ✅ |
| FR-10 | Option A transport | ❌ Removed (2026-06-12) | ❌ |
| FR-11 | Option B transport | `test_bridge_unit`, `test_bridge_negatives`, `test_flex_capabilities_b` | 🟡 |
| FR-12 | Identical protocol both transports | ❌ Removed | ❌ |
| FR-13 | Flutter transport switch | ❌ Removed | ❌ |
| FR-14 | Terminal transport switch | ❌ Removed | ❌ |
| FR-15 | Bridge auto-detect CANoe/CANalyzer | `____` | ⬜ |
| FR-16 | Reconnection | `test_reconnect` | ⬜ |
| FR-17 | Flutter feature set | `____` | ⬜ |
| FR-18 | Terminal feature set | `test_flex_capabilities_b` | ✅ |
| FR-20 | Mock ECU responds to core SIDs | `test_mock_uds` | ✅ |
| FR-22 | Mock seed/key matches DLL | `test_mock_uds::test_security_*` | ✅ |
| FR-23 | Mock NRC injection | `test_mock_uds::test_inject_next_nrc`, `test_server_negatives`, `test_bridge_negatives` | ✅ |

| NFR-4 | Byte-accurate encode/decode | `test_bridge_unit` | 🟡 |

> Add NFR rows (latency NFR-3, COM serialization NFR-10) as they get coverage. NFR-4 verified on mock (Option B loopback); real Vector/COM pending.

---

## 4. Recent changes (newest first)

| Date | PR / commit | Change | Topology | Tool |
|------|-------------|--------|----------|------|
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
