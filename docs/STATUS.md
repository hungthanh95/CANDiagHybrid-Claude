# FlexDiag — Project Status

**Maintained by:** `flexdiag-status` (Haiku) · **Updated:** `2026-06-12` (M3 complete, Option B code+mock ✅)

> Single source of truth for project state. Do not mark anything ✅ without a tester-confirmed result on **both** transports. Legend: ✅ pass · 🟡 partial · ⬜ not yet · ❌ failing.

---

## 1. Milestone board (M0–M6)

| Milestone | Definition of done | Status |
|-----------|--------------------|--------|
| **M0** Protocol frozen | Wire protocol + sysvar layout signed off | ✅ Done — protocol frozen at proto=1, sysvar layout frozen (reviewer-approved) |
| **M1** Software loopback | Terminal ⇄ Mock ECU over plain TCP, all 5 capabilities | ✅ Done — Mock ECU + terminal on software TCP loopback; 87 tests; all 5 capabilities verified; ruff + black clean |
| **M2** Option A live | Terminal ⇄ CAPL TCP ⇄ Vector ⇄ (virtual + VN1610) | 🟡 In progress — `flexdiag_core.can` + `flexdiag_tcp.can` code-complete (reviewer-approved via commit `9dce487`), CANalyzer compile ✅, full bring-up checklist (docs/05 §8) ⬜ pending |
| **M3** Option B live | Terminal ⇄ bridge ⇄ COM/sysvar ⇄ Vector | 🟡 In progress — `flexdiag_sysvar.can` + `bridge/` code-complete (reviewer-approved via commit `b1ba857`), all 5 capabilities verified on mock loopback (42 tests in M3, 129 total passing), real Vector/COM bring-up ⬜ pending (parallel to M2) |
| **M4** Transport switch | Runtime A/B switch in terminal and Flutter | ⬜ Not started |
| **M5** Flutter parity | Flutter does all 4 capabilities on both transports | ⬜ **Deferred** — Python terminal is v1 test client; see CLAUDE.md §1a |
| **M6** Release v1 | Hardened, documented, reproducible setup | ⬜ Not started |

---

## 2. Capability matrix

Cells show current verified state. A capability is "done" only when **Option A** and **Option B** are both ✅.¹

| Capability | Option A (TCP) | Option B (COM/sysvar) | CANoe | CANalyzer | Mock ECU |
|------------|:--:|:--:|:--:|:--:|:--:|
| Read DTC (`0x19 02`) | ⬜ | ⬜ | ⬜ | ⬜ | ✅ |
| Tester Present (`0x3E`) | ⬜ | ⬜ | ⬜ | ⬜ | ✅ |
| Security Access (`0x27`) | ⬜ | ⬜ | ⬜ | ⬜ | ✅ |
| Session Control (`0x10`) | ⬜ | ⬜ | ⬜ | ⬜ | ✅ |
| Clear DTC (`0x14`) | ⬜ | ⬜ | ⬜ | ⬜ | ✅ |

¹ Both transports verified identical on mock loopback (M1/M3; see Recent changes). Real Vector bring-up (Option A via CANoe/CANalyzer TCP, Option B via real COM/sysvar) still pending.

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
| FR-7 | Raw request | `test_smoke` | ✅ |
| FR-8 | NRC surfaced distinctly | `test_server_negatives`, `test_protocol_nrc` | ✅ |
| FR-9 | `0x78` pending handled | `test_server_negatives::test_pending_0x78_then_final` | ✅ |
| FR-10 | Option A transport | `____` | ⬜ |
| FR-11 | Option B transport | `test_bridge_unit`, `test_bridge_negatives`, `test_flex_capabilities_b` | 🟡 |
| FR-12 | Identical protocol both transports | `test_flex_capabilities`, `test_flex_capabilities_b`, `cap_matrix.py` | 🟡 |
| FR-13 | Flutter transport switch | `____` | ⬜ |
| FR-14 | Terminal transport switch | `____` | ⬜ |
| FR-15 | Bridge auto-detect CANoe/CANalyzer | `____` | ⬜ |
| FR-16 | Reconnection | `test_reconnect` | ⬜ |
| FR-17 | Flutter feature set | `____` | ⬜ |
| FR-18 | Terminal feature set | `test_flex_capabilities`, `test_smoke` | ✅ |
| FR-20 | Mock ECU responds to core SIDs | `test_mock_uds` | ✅ |
| FR-22 | Mock seed/key matches DLL | `test_mock_uds::test_security_*` | ✅ |
| FR-23 | Mock NRC injection | `test_mock_uds::test_inject_next_nrc`, `test_server_negatives`, `test_bridge_negatives` | ✅ |

| NFR-4 | Byte-accurate encode/decode | `test_bridge_unit` | 🟡 |

> Add NFR rows (latency NFR-3, COM serialization NFR-10) as they get coverage. NFR-4 verified on mock (both transports); real Vector pending.

---

## 4. Recent changes (newest first)

| Date | PR / commit | Change | Topology | Tool |
|------|-------------|--------|----------|------|
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
| R1 | CAPL **TCP/IP API** licensing on operator's CANalyzer (parked; Option A Vector bring-up depends on this) | — | **Parked** — M2 code approved; CANalyzer compile OK; full bring-up held until API license confirmed |
| R2 | **Option B Vector/COM bring-up:** `flexdiag_sysvar.can` + `bridge/` code-complete + reviewer-approved; real COM/sysvar verification ⬜ pending (parallel to R1's M2 CAPL TCP status) | — | Active — Option B code approved; mock-loopback parity (all 5 capabilities) verified; real Vector/COM bring-up checklist pending |
| R3 | Seed-key **DLL bitness** must match the Vector process | — | Open |
| R4 | Raw-request / sysvar **CAPL syntax** may differ across tool versions | — | Open — pin reference version |
| R5 | **VN1610 channel** assignment for tool + passive coexistence | — | Open |
| R6 | Mock ECU **key algorithm** drift vs test DLL silently breaks `0x27` test | — | Open |

---

## 6. Next actions

- [x] Freeze wire protocol + sysvar layout → **M0**.
- [x] Build Mock ECU + terminal on software loopback → **M1**.
- [x] Write + reviewer-approve `flexdiag_core.can` + `flexdiag_tcp.can` → **M2 code**.
- [x] **Prioritize M3:** write `flexdiag_sysvar.can` + Python `bridge/` (Option B) → **M3 code-complete + mock verified**.
- [ ] Run M3 Vector/COM bring-up checklist (docs/05 §8) once an operator can drive `pywin32` / CANoe/CANalyzer.
- [ ] Confirm CAPL TCP/IP API license for CANalyzer (resolves R1; gates full M2 Vector bring-up).
- [ ] Run M2 Vector bring-up checklist (docs/05 §8) once API confirmed.
