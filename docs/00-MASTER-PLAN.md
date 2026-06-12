# Master Plan — CAN Diagnostic Tool

**Project codename:** FlexDiag
**Document:** Master Plan
**Status:** Draft v1.0
**Target stack:** Flutter (UI) · Python (bridge/terminal/mock) · CAPL (in-tool node) · Vector CANoe/CANalyzer · Vector VN1610

---

## 1. Purpose

Build a UDS (ISO 14229) diagnostic tool whose user-facing logic runs in a modern Flutter UI, while the actual CAN traffic is produced by **Vector CANoe or CANalyzer** driving a **VN1610** interface. The tool focuses on a small, well-defined set of diagnostic services and must run **without a CDD/ODX file** by relying on the tool's built-in *Basic Diagnostics (UDS)* template and CAPL raw-request primitives.

The system must support **two interchangeable backend transports** between the UI and the Vector tool, selectable at runtime:

- **Option A — CAPL TCP Server:** a CAPL node inside CANoe/CANalyzer opens a TCP socket; the client connects directly.
- **Option B — COM API + System Variables:** a thin Python bridge uses the Vector COM API to exchange data through System Variables; the client connects to the bridge over WebSocket.

Two clients consume these backends:

- **Flutter UI** — the production operator interface.
- **Python terminal UI** — a developer/test client used for protocol bring-up, regression testing, and direct ECU interaction.

A **Mock ECU** (Python) emulates UDS responses so the full stack can be exercised without real hardware or a real ECU.

---

## 2. Goals and Non-Goals

### 2.1 Goals

- Support four diagnostic capabilities end-to-end:
  - **Read DTC** (service `0x19`, primarily sub-function `0x02` *reportDTCByStatusMask*).
  - **Tester Present** (service `0x3E`, periodic, suppress-positive-response).
  - **Security Access** (service `0x27`, seed request + key send).
  - **Key generation** via the Vector seed-key DLL (`GenerateKeyEx` convention), invoked from CAPL.
- Run identically on **CANoe and CANalyzer** with no CDD.
- Allow runtime switching between Option A and Option B from **both** the Flutter UI and the Python terminal.
- Provide a **Mock ECU** for offline development and CI.
- Ship a reproducible **setup guide** for the Vector configuration (channels, diagnostic layer, system variables, seed-key DLL).

### 2.2 Non-Goals

- No CDD/ODX authoring or symbolic decoding inside the Vector tool. DTC/DID interpretation is done client-side in Dart/Python.
- No ECU flashing/reprogramming (`0x34`/`0x36`/`0x37`) in v1.
- No direct hardware access from the clients (the Vector tool always owns the VN1610 in this architecture; direct `vxlapi` access is explicitly out of scope per requirement).
- No multi-ECU orchestration in v1 (single diagnostic target; design leaves room to extend).

---

## 3. Scope of diagnostic services (v1)

| Service | SID | Sub-function(s) | Notes |
|---------|-----|-----------------|-------|
| DiagnosticSessionControl | `0x10` | `0x01` default, `0x03` extended | Needed before security on most ECUs |
| ReadDTCInformation | `0x19` | `0x02` byStatusMask | Core feature |
| ClearDiagnosticInformation | `0x14` | — | Optional companion to DTC read |
| SecurityAccess | `0x27` | `0x01`/`0x02` (and odd/even pairs) | Seed/key via CAPL DLL |
| TesterPresent | `0x3E` | `0x80` suppress-positive | Periodic keep-alive |

> Session control and clear-DTC are included because security access and a usable DTC workflow depend on them in practice.

---

## 4. Workstreams and deliverables

| # | Workstream | Key deliverables |
|---|------------|------------------|
| W1 | **Vector configuration** | CANoe `.cfg` + CANalyzer `.cfg`, diagnostic layer (Basic UDS), sysvar namespace, seed-key DLL attached, channel mapping |
| W2 | **CAPL backend** | `flexdiag_core.can` (diagnostic primitives), `flexdiag_tcp.can` (Option A), `flexdiag_sysvar.can` (Option B) |
| W3 | **Python bridge (Option B)** | COM + sysvar bridge exposing WebSocket; auto-detects CANoe vs CANalyzer |
| W4 | **Wire protocol** | Single line-based protocol spec used by A and B identically |
| W5 | **Flutter UI** | Operator app: connection/transport switch, DTC view, security flow, tester-present toggle |
| W6 | **Python terminal UI** | TUI client with same protocol, both transports, scripting hooks |
| W7 | **Mock ECU** | Python UDS responder (seed/key, DTC table, NRC injection) |
| W8 | **Docs** | This set: master plan, architecture, requirements, technical detail, rules, setup guide |

---

## 5. Phasing

### Phase 0 — Protocol & contracts (foundation)
Define the wire protocol (W4) and the system-variable layout. Everything else depends on this being frozen first. Exit criteria: protocol spec reviewed, message catalogue complete.

### Phase 1 — Mock-first vertical slice
Build the **Mock ECU** (W7) and the **Python terminal** (W6) against **Option A** only, talking to a *software* TCP loopback (no Vector yet). Prove the protocol round-trips a `19 02 FF` request and a `27` seed/key exchange end-to-end in pure software. Exit criteria: terminal reads mock DTCs and unlocks mock security over TCP.

### Phase 2 — Vector integration, Option A
Stand up the Vector configuration (W1) and the CAPL TCP node (W2). Point the Python terminal at the real CAPL TCP server driving the Mock ECU over a **virtual CAN channel**, then over the **VN1610** to a real ECU. Exit criteria: terminal performs all four capabilities through CANoe *and* CANalyzer.

### Phase 3 — Option B (COM + sysvar)
Add the sysvar CAPL node and the Python bridge (W3). Validate the same capabilities through the bridge. Exit criteria: transport switch works in the terminal; identical protocol behaviour on A and B.

### Phase 4 — Flutter UI
Build the operator UI (W5) consuming the frozen protocol, with the transport switch. Exit criteria: feature parity with the terminal for the four capabilities.

### Phase 5 — Hardening & docs
Error handling, reconnection, NRC surfacing, timeouts, logging, and finalising the setup guide (W8). Exit criteria: docs let a new engineer reproduce the environment from scratch.

---

## 6. Milestones

| Milestone | Definition of done |
|-----------|--------------------|
| M0 Protocol frozen | Wire protocol + sysvar layout signed off |
| M1 Software loopback | Terminal ⇄ Mock ECU over plain TCP, all 4 capabilities |
| M2 Option A live | Terminal ⇄ CAPL TCP ⇄ Vector ⇄ (virtual + VN1610) |
| M3 Option B live | Terminal ⇄ bridge ⇄ COM/sysvar ⇄ Vector |
| M4 Transport switch | Runtime A/B switch in terminal and Flutter |
| M5 Flutter parity | Flutter does all 4 capabilities on both transports |
| M6 Release v1 | Hardened, documented, reproducible setup |

---

## 7. Key risks and mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| CAPL **TCP/IP API not licensed/available** in the target CANalyzer build | Option A unusable on that seat | Option B (COM + sysvar) is the compatibility fallback; verify TCP API early in Phase 2 with a one-node compile test |
| CANalyzer **COM diagnostic object** is limited vs CANoe | Can't drive diagnostics via COM directly | Architecture deliberately keeps diagnostics inside CAPL; COM only moves sysvars, which both tools expose |
| **Seed-key DLL bitness** (32 vs 64) mismatch | Key generation fails | DLL is attached to the *Vector tool* and called by CAPL `diagGenerateKeyFromSeed`, so client bitness is irrelevant; match DLL bitness to the CANoe/CANalyzer process |
| Raw-request CAPL syntax differs across **tool versions** | CAPL won't compile | Pin a reference version in the setup guide; isolate version-sensitive calls in `flexdiag_core.can` |
| **VN1610 channel contention** between the tool and other apps | Bus access conflicts | Document Vector Hardware Config channel assignment; tool owns the channel during measurement |
| No CDD → **manual byte building** errors | Wrong requests sent | Centralise service encoders in one module per client; cover with Mock ECU tests |
| COM requires **STA threading / message pump** | Bridge hangs or misses events | Run COM on a dedicated thread with proper `CoInitialize`; never call COM from the async WebSocket handler directly |

---

## 8. Success criteria

1. From a clean machine, an engineer can follow the setup guide and reach M2 within one working session.
2. The same Flutter build performs all four capabilities against a real ECU through **either** CANoe or CANalyzer, on **either** transport, with no code change — only a config switch.
3. The Mock ECU lets the entire client stack be developed and regression-tested with no Vector hardware present.

---

## 9. Repository layout (proposed)

```
flexdiag/
├── docs/                      # this documentation set
├── vector/
│   ├── canoe/                 # CANoe .cfg + assets
│   ├── canalyzer/             # CANalyzer .cfg + assets
│   ├── capl/
│   │   ├── flexdiag_core.can      # diagnostic primitives (shared)
│   │   ├── flexdiag_tcp.can       # Option A transport
│   │   └── flexdiag_sysvar.can    # Option B transport
│   └── sysvars/flexdiag.vsysvar   # System Variable definitions
├── bridge/                    # Python COM↔WebSocket bridge (Option B)
├── mock_ecu/                  # Python UDS responder
├── terminal/                  # Python TUI test client
├── flutter_app/              # Flutter operator UI
└── protocol/                 # shared protocol spec + reference codecs
```

---

## 10. Document map

| Document | Audience | Purpose |
|----------|----------|---------|
| `00-MASTER-PLAN.md` *(this)* | All | Scope, phases, risks |
| `01-SYSTEM-ARCHITECTURE.md` | Architects, devs | Components, data flow, both transports |
| `02-SYSTEM-REQUIREMENTS.md` | All | Functional + non-functional + environment |
| `03-TECHNICAL-DETAIL.md` | Implementers | Protocol, CAPL, sysvars, bridge, mock, codecs |
| `04-RULES-AND-CONVENTIONS.md` | Devs | Coding/protocol/git rules |
| `05-CANOE-CANALYZER-SETUP.md` | Integrators | Step-by-step Vector setup |
