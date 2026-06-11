# FlexDiag — CAN Diagnostic Tool

A UDS (ISO 14229) diagnostic tool with a **Flutter** operator UI and a **Python terminal** test client, both driving **Vector CANoe/CANalyzer + VN1610** — **without a CDD**. Two interchangeable transports connect the clients to the Vector tool, switchable at runtime:

- **Option A — CAPL TCP server** (client connects directly to a CAPL TCP node).
- **Option B — COM API + System Variables** (Python bridge over WebSocket).

Capabilities (v1): **Read DTC**, **Tester Present**, **Security Access** (seed/key via the Vector seed-key DLL inside CAPL), plus session control and clear-DTC. A **Mock ECU** lets the whole stack run offline.

```
Flutter UI ┐                          ┌ flexdiag_tcp.can ┐
           ├─ same wire protocol ─────┤                  ├─ flexdiag_core.can ─ Basic Diagnostics (UDS) ─ VN1610 ─ ECU/Mock
Python TUI ┘   (A: TCP / B: WS+COM)   └ flexdiag_sysvar  ┘                       + seed-key DLL
```

## Read in this order

| # | Document | What it covers |
|---|----------|----------------|
| 0 | [00-MASTER-PLAN.md](00-MASTER-PLAN.md) | Scope, goals, phasing, milestones, risks, repo layout |
| 1 | [01-SYSTEM-ARCHITECTURE.md](01-SYSTEM-ARCHITECTURE.md) | Components, data flow, both transports, key ADRs |
| 2 | [02-SYSTEM-REQUIREMENTS.md](02-SYSTEM-REQUIREMENTS.md) | Functional + non-functional + environment requirements |
| 3 | [03-TECHNICAL-DETAIL.md](03-TECHNICAL-DETAIL.md) | Wire protocol, sysvar layout, CAPL, bridge, mock ECU, codecs |
| 4 | [04-RULES-AND-CONVENTIONS.md](04-RULES-AND-CONVENTIONS.md) | Protocol/CAPL/Python/Dart/git/testing rules |
| 5 | [05-CANOE-CANALYZER-SETUP.md](05-CANOE-CANALYZER-SETUP.md) | Step-by-step Vector setup + bring-up checklist |

## Quick start (suggested path)

1. Read the **Master Plan** §5 (phasing) — build mock-first.
2. Freeze the **wire protocol** (Technical Detail §1) and **sysvar layout** (§2). This is milestone **M0**.
3. Build **Mock ECU** + **Python terminal** on a software loopback → all four capabilities (M1).
4. Follow the **Setup Guide** to stand up Vector + Option A, then Option B.
5. Build the **Flutter UI** against the frozen protocol last.

## Key constraints

- **No CDD** — uses the tool's built-in *Basic Diagnostics (UDS)* template; all DTC/DID decoding is client-side.
- **Diagnostics live in CAPL**, not COM — so Option B works identically on CANoe and CANalyzer (COM only moves System Variables).
- **The Vector tool owns the VN1610**; clients never call `vxlapi` directly.
- **Seed-key DLL** is attached to the tool and called by CAPL; client bitness is irrelevant, DLL bitness must match the tool process.
