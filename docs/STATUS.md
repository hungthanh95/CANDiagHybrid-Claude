# FlexDiag — Project Status

**Maintained by:** `flexdiag-status` (Haiku) · **Updated:** `2026-06-12`

> Single source of truth for project state. Do not mark anything ✅ without a tester-confirmed result on **both** transports. Legend: ✅ pass · 🟡 partial · ⬜ not yet · ❌ failing.

---

## 1. Milestone board (M0–M6)

| Milestone | Definition of done | Status |
|-----------|--------------------|--------|
| **M0** Protocol frozen | Wire protocol + sysvar layout signed off | ✅ Done — protocol frozen at proto=1, sysvar layout frozen (reviewer-approved) |
| **M1** Software loopback | Terminal ⇄ Mock ECU over plain TCP, all 5 capabilities | ✅ Done — Mock ECU + terminal on software TCP loopback; 87 tests; all 5 capabilities verified; ruff + black clean |
| **M2** Option A live | Terminal ⇄ CAPL TCP ⇄ Vector ⇄ (virtual + VN1610) | ⬜ Not started |
| **M3** Option B live | Terminal ⇄ bridge ⇄ COM/sysvar ⇄ Vector | ⬜ Not started |
| **M4** Transport switch | Runtime A/B switch in terminal and Flutter | ⬜ Not started |
| **M5** Flutter parity | Flutter does all 4 capabilities on both transports | ⬜ Not started |
| **M6** Release v1 | Hardened, documented, reproducible setup | ⬜ Not started |

---

## 2. Capability matrix

Cells show current verified state. A capability is "done" only when **Option A** and **Option B** are both ✅.

| Capability | Option A (TCP) | Option B (COM/sysvar) | CANoe | CANalyzer | Mock ECU |
|------------|:--:|:--:|:--:|:--:|:--:|
| Read DTC (`0x19 02`) | ⬜ | ⬜ | ⬜ | ⬜ | ✅ |
| Tester Present (`0x3E`) | ⬜ | ⬜ | ⬜ | ⬜ | ✅ |
| Security Access (`0x27`) | ⬜ | ⬜ | ⬜ | ⬜ | ✅ |
| Session Control (`0x10`) | ⬜ | ⬜ | ⬜ | ⬜ | ✅ |
| Clear DTC (`0x14`) | ⬜ | ⬜ | ⬜ | ⬜ | ✅ |

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
| FR-11 | Option B transport | `____` | ⬜ |
| FR-12 | Identical protocol both transports | `____` | ⬜ |
| FR-13 | Flutter transport switch | `____` | ⬜ |
| FR-14 | Terminal transport switch | `____` | ⬜ |
| FR-15 | Bridge auto-detect CANoe/CANalyzer | `____` | ⬜ |
| FR-16 | Reconnection | `test_reconnect` | ⬜ |
| FR-17 | Flutter feature set | `____` | ⬜ |
| FR-18 | Terminal feature set | `test_flex_capabilities`, `test_smoke` | ✅ |
| FR-20 | Mock ECU responds to core SIDs | `test_mock_uds` | ✅ |
| FR-22 | Mock seed/key matches DLL | `test_mock_uds::test_security_*` | ✅ |
| FR-23 | Mock NRC injection | `test_mock_uds::test_inject_next_nrc`, `test_server_negatives` | ✅ |

> Add NFR rows (latency NFR-3, byte-accuracy NFR-4, COM serialization NFR-10) as they get coverage.

---

## 4. Recent changes (newest first)

| Date | PR / commit | Change | Topology | Tool |
|------|-------------|--------|----------|------|
| 2026-06-12 | `10b04e1` | M1: Mock ECU + terminal + protocol codec on software TCP loopback; 87 tests (codec, mock UDS, server negatives, .flex regression per capability); ruff+black clean | software loopback | n.a. |
| 2026-06-12 | `____` | M0: froze wire protocol (proto=1) + Diag sysvar layout in docs/03-TECHNICAL-DETAIL.md; added Diag::RspKind sysvar; moved 00/01/02/03/05/STATUS/RUNBOOK into docs/ | — | n.a. |
| `____-__-__` | `____` | _(initial scaffold)_ | — | — |

> Topology = software loopback / virtual CAN / VN1610+real ECU. Tool = CANoe / CANalyzer / n.a.

---

## 5. Open risks & blockers (live)

| # | Risk / blocker | Owner | Status |
|---|----------------|-------|--------|
| R1 | CAPL **TCP/IP API** availability on the target CANalyzer build unverified (blocks Option A on that seat) | — | Open — verify early in M2 |
| R2 | Seed-key **DLL bitness** must match the Vector process | — | Open |
| R3 | Raw-request / sysvar **CAPL syntax** may differ across tool versions | — | Open — pin reference version |
| R4 | **VN1610 channel** assignment for tool + passive coexistence | — | Open |
| R5 | Mock ECU **key algorithm** drift vs test DLL silently breaks `0x27` test | — | Open |

---

## 6. Next actions

- [x] Freeze wire protocol + sysvar layout → **M0**.
- [x] Build Mock ECU + terminal on software loopback → **M1**.
- [ ] Verify CAPL TCP/IP API on the target CANalyzer build (resolves R1).
- [ ] Stand up Vector config per `docs/05` → **M2**.
