# System Architecture — FlexDiag

**Document:** System Architecture
**Status:** Draft v1.0

---

## 1. Context

FlexDiag separates **UI/logic** (Flutter or Python terminal) from **CAN execution** (CANoe/CANalyzer + VN1610). The Vector tool is the diagnostic engine: it owns the hardware, the ISO-TP transport, and the seed-key DLL. Clients never touch the VN1610 directly.

A single transport (Option B: COM API + System Variables, exposed to clients over WebSocket) connects clients to the Vector tool, speaking one wire protocol (see Technical Detail).

> **Removed (2026-06-12):** Option A (a CAPL TCP server transport) was removed due to uncertain CAPL TCP/IP API licensing on the operator's CANalyzer. See `docs/STATUS.md` §5 (R1) and ADR-3 below.

---

## 2. High-level diagram

```
┌──────────────────────────────┐        ┌──────────────────────────────┐
│        Flutter UI            │        │     Python Terminal UI       │
│  (operator app)              │        │  (developer/test client)     │
│                              │        │                              │
│  • DTC view                  │        │  • REPL / scripted tests     │
│  • Security flow             │        │  • raw request sender        │
│  • Tester Present toggle     │        │  • protocol logger           │
└───────────────┬──────────────┘        └───────────────┬──────────────┘
                │                                        │
                │   same wire protocol (line-based,      │
                │   Option B: WebSocket)                 │
                │                                        │
        ┌───────┴───────────────────────────────────────┴───────┐
        │                                                        │
        │                ┌───────────────────────────────┐      │
        └───────────────►│   Python Bridge (Option B)    │◄─────┘
                         │  • WebSocket server          │
                         │  • Vector COM client (STA)   │
                         │  • sysvar read/write + events│
                         └──────┬───────────────────────┘
                                │ COM API
                                │ (CANoe.Application /
                                │  CANalyzer.Application)
                                ▼
┌───────────────────────────────────────────────────────────────────┐
│                    CANoe / CANalyzer (measurement)                 │
│                                                                   │
│            ┌────────────────────┐   ┌────────────┐                │
│            │ flexdiag_sysvar.can│   │ System Vars│                │
│            │  (Option B node)   │◄──┤  Diag::*   │                │
│            └─────────┬──────────┘   └────────────┘                │
│                      │                                            │
│                      ▼                                            │
│            ┌────────────────────────────┐                         │
│            │     flexdiag_core.can      │                         │
│            │  diagSendRequest / response│                         │
│            │  diagGenerateKeyFromSeed   │                         │
│            │  diagStart/StopTesterPresent│                        │
│            └────────────┬───────────────┘                         │
│                         ▼                                         │
│            ┌────────────────────────────┐   ┌──────────────────┐  │
│            │ Basic Diagnostics (UDS)    │   │  Seed-Key DLL    │  │
│            │ ISO-TP / 14229 template    │◄──┤  GenerateKeyEx   │  │
│            └────────────┬───────────────┘   └──────────────────┘  │
└─────────────────────────┼─────────────────────────────────────────┘
                          ▼
                    ┌───────────┐
                    │  VN1610   │
                    └─────┬─────┘
                          │ CAN
            ┌─────────────┴─────────────┐
            ▼                           ▼
   ┌─────────────────┐         ┌─────────────────┐
   │   Real ECU      │   or    │  Mock ECU (PC)  │
   │                 │         │  on virtual CAN │
   └─────────────────┘         └─────────────────┘
```

---

## 3. Components

### 3.1 Clients

**Flutter UI** — operator-facing. Owns: connection management, service-byte construction, response/DTC decoding, security flow orchestration (as a single user action), tester-present toggle, and logging. Stateless with respect to the ECU beyond UI session state.

**Python terminal UI** — developer-facing. Same protocol, plus a raw-bytes escape hatch, scripting, and verbose protocol tracing. Used to bring up the protocol before the Flutter UI exists and to run regression scripts against the Mock ECU.

Both clients share a conceptual **protocol client library** (implemented once per language) so behaviour is identical.

### 3.2 Transport

**Option B — COM + System Variables.** `flexdiag_sysvar.can` reacts to changes on a `Diag::*` sysvar namespace. The **Python bridge** writes requests to sysvars over COM and listens for response sysvar change events, re-exposing everything as WebSocket to the client. COM diagnostic objects are *not* used — only sysvars — which is why it works identically on CANalyzer and CANoe.

### 3.3 In-tool CAPL layer

**`flexdiag_core.can`** — the single place that talks to the diagnostic layer: builds raw requests, sends them, receives responses, runs the seed→key→send-key dance via the DLL, and controls tester present. Transport nodes call into this core; the core is transport-agnostic.

**Basic Diagnostics (UDS) layer** — built-in tool template providing ISO-TP segmentation/flow-control, P2/P2* timing, NRC `0x78` handling, and the request/response object model — all without a CDD.

**Seed-Key DLL** — attached to the diagnostic layer; invoked by CAPL `diagGenerateKeyFromSeed`. Client bitness is irrelevant; DLL bitness must match the Vector process.

### 3.4 Hardware / ECU

**VN1610** — owned by the measurement. Can be assigned via Vector Hardware Config to coexist with other passive applications if needed.

**Mock ECU** — a Python process acting as a UDS server on a **virtual CAN channel** (or a second physical channel). Lets the whole chain run with no real ECU. Supports a configurable DTC table, seed/key algorithm matching the DLL (or a known test algorithm), session control, and deliberate NRC injection for negative-path testing.

---

## 4. Data flow

### 4.1 Request/response (e.g. Read DTC)

```
Client                Bridge/Transport     CAPL core            Diag layer      ECU
  │  REQ 19 02 FF        │                    │                    │             │
  ├─────────────────────►│                    │                    │             │
  │                      │  (on sysvar write) │                    │             │
  │                      ├───────────────────►│ SendRawDiag()      │             │
  │                      │                    ├───────────────────►│ 19 02 FF    │
  │                      │                    │                    ├────────────►│
  │                      │                    │                    │  59 02 ...  │
  │                      │                    │  on diagResponse   │◄────────────┤
  │                      │                    │◄───────────────────┤             │
  │                      │  RSP 59 02 ...     │                    │             │
  │  RSP 59 02 ...       │◄───────────────────┤                    │             │
  │◄─────────────────────┤                    │                    │             │
```

### 4.2 Security access (single client action, multi-step inside CAPL)

```
Client → SEC 01
  CAPL: send 27 01 ──► ECU ──► 67 01 <seed>
  CAPL: diagGenerateKeyFromSeed(<seed>) via DLL ──► <key>
  CAPL: send 27 02 <key> ──► ECU ──► 67 02   (unlocked)
  CAPL: (optional) diagStartTesterPresent()
Client ◄ OK SEC 01           (or NRC 7F 27 35 invalidKey, etc.)
```

The seed/key exchange is hidden from the client: the DLL lives next to the tool, so CAPL is the natural place to run it.

### 4.3 Tester present (periodic, fire-and-forget)

```
Client → TP START
  CAPL: diagStartTesterPresent()   # tool emits 3E 80 at configured period
Client ◄ OK TP

Client → TP STOP
  CAPL: diagStopTesterPresent()
Client ◄ OK TP
```

---

## 5. Transport interface

Clients depend on a `Transport`/`DiagService` interface (CLAUDE.md rule 4), implemented today by `WebSocketTransport(url)` → Option B (bridge). Feature code is unaware of which concrete implementation is active; this keeps the door open for a future alternate implementation without touching feature code, but only Option B exists/ships in v1.

---

## 6. Deployment topologies

| Topology | Use |
|----------|-----|
| **All-software** (no Vector) | Terminal ⇄ WebSocket ⇄ Python bridge (`bridge --fake`) ⇄ Mock ECU (`mock_ecu.uds.Ecu`). Earliest dev/CI; no Vector needed. |
| **Vector + virtual CAN + Mock ECU** | Full Vector path, virtual bus, mock target. Validates CAPL + the Option B transport without a real ECU. |
| **Vector + VN1610 + real ECU** | Production. Option B, CANoe or CANalyzer. |

---

## 7. Key design decisions (ADR summaries)

**ADR-1: Keep diagnostics in CAPL, not COM.**
*Context:* CANalyzer's COM diagnostic surface is limited; CANoe's is richer. *Decision:* All diagnostic logic lives in CAPL (`flexdiag_core.can`); COM is used only to move System Variables in Option B. *Consequence:* One diagnostic implementation runs on both tools; the bridge stays trivial and tool-agnostic.

**ADR-2: No CDD — raw requests + client-side decoding.**
*Context:* No CDD/ODX available. *Decision:* Use Basic Diagnostics (UDS) for transport + raw request primitives; decode DTC/DID in Dart/Python. *Consequence:* No symbolic names in-tool, but full control and zero licensing dependency on description files.

**ADR-3: One wire protocol for both transports.**
*Context:* Two transports risk two protocols. *Decision:* A single line-based protocol sits above TCP and WebSocket alike. *Consequence:* Clients implement features once; switching is purely a transport concern.

**Superseded 2026-06-12:** Option A (CAPL TCP) removed; only Option B (COM + sysvar bridge) remains. This ADR's rationale (one protocol shared by two transports) is preserved as historical context; in practice only Option B is implemented.

**ADR-4: Mock-first development.**
*Context:* Hardware/ECU access is scarce and slow. *Decision:* Build Mock ECU + terminal first, on a software loopback. *Consequence:* The client stack is testable offline and in CI; Vector integration is added without rewriting clients.

**ADR-5: Bridge runs COM on a dedicated STA thread.**
*Context:* COM needs single-threaded apartment + message pump; WebSocket server is async. *Decision:* COM lives on its own thread with a queue between it and the async server. *Consequence:* No COM re-entrancy hangs; sysvar change events are delivered reliably.

---

## 8. Cross-cutting concerns

**Logging.** Every layer logs the raw protocol line with a direction and timestamp. CAPL writes to the Write window; the bridge and clients keep rolling logs. A request can be traced end to end by its sequence id.

**Correlation.** Each request carries a client-generated sequence id echoed in the response so concurrent/queued requests match up (see Technical Detail §protocol).

**Timeouts.** Two layers: the diagnostic layer enforces P2/P2* (ISO 14229); the client enforces a higher wall-clock timeout as a safety net and surfaces a clear error if the tool/bridge goes silent.

**Reconnection.** Clients detect transport drop and attempt bounded reconnect; in-flight requests are failed with a transport-error result, never silently lost.

**Security of the channel.** The WebSocket bridge binds to `127.0.0.1` by default (same machine as the Vector tool). Remote operation is opt-in and out of scope for v1 hardening.
