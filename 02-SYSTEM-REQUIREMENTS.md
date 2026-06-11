# System Requirements — FlexDiag

**Document:** System Requirements
**Status:** Draft v1.0

Requirement IDs: **FR** = functional, **NFR** = non-functional, **ENV** = environment/constraint. Priority: **M** must, **S** should, **C** could.

---

## 1. Functional requirements

### 1.1 Diagnostic capabilities

| ID | Pri | Requirement |
|----|-----|-------------|
| FR-1 | M | The system shall read DTCs via UDS `0x19 0x02` (reportDTCByStatusMask) with a configurable status mask (default `0xFF`) and return the raw `59 02 <mask> <DTC+status>...` payload to the client. |
| FR-2 | M | The system shall decode each 4-byte DTC record (3-byte DTC + 1-byte status) into ISO-15031 format (`P/C/B/U` + hex) **on the client side**. |
| FR-3 | S | The system shall clear DTCs via UDS `0x14` with a configurable group (default `FF FF FF`). |
| FR-4 | M | The system shall start/stop **periodic Tester Present** (`0x3E 0x80`, suppress positive response) using the tool's built-in tester-present mechanism. |
| FR-5 | M | The system shall perform **Security Access**: request seed (`0x27 <oddLevel>`), generate the key via the seed-key DLL inside CAPL, and send the key (`0x27 <evenLevel>`), reporting unlocked/failed to the client. |
| FR-6 | S | The system shall perform **DiagnosticSessionControl** (`0x10 <session>`) so extended session can be entered before security. |
| FR-7 | S | The system shall send an **arbitrary raw UDS request** (operator-supplied byte string) and return the raw response — primarily for the terminal client. |
| FR-8 | M | For every request the system shall surface **negative responses** (`7F <SID> <NRC>`) distinctly from positive responses, including the NRC code. |
| FR-9 | S | The system shall handle response-pending (`NRC 0x78`) transparently via the diagnostic layer and only report the final response. |

### 1.2 Transport / connectivity

| ID | Pri | Requirement |
|----|-----|-------------|
| FR-10 | M | The system shall support **Option A**: a CAPL TCP server inside CANoe/CANalyzer that a client connects to directly. |
| FR-11 | M | The system shall support **Option B**: a Python bridge using the Vector COM API + System Variables, exposed to clients over WebSocket. |
| FR-12 | M | Both transports shall expose the **identical wire protocol**, so clients need no per-transport feature code. |
| FR-13 | M | The **Flutter UI** shall let the operator switch transport (A/B) at runtime without restarting the app. |
| FR-14 | M | The **Python terminal** shall let the user switch transport (A/B) at runtime. |
| FR-15 | M | The Option B bridge shall connect to **either** `CANoe.Application` **or** `CANalyzer.Application` (auto-detect or configurable), with no other code change. |
| FR-16 | S | Clients shall automatically attempt bounded **reconnection** on transport loss and fail in-flight requests with a clear error. |

### 1.3 Clients

| ID | Pri | Requirement |
|----|-----|-------------|
| FR-17 | M | The **Flutter UI** shall provide: connect/disconnect, transport switch, session control, read DTC (with decoded table), clear DTC, security unlock (single action), tester-present toggle, and a live log. |
| FR-18 | M | The **Python terminal** shall provide: connect/disconnect, transport switch, all FR-1..FR-9 operations, raw-request entry, scripted command files, and verbose protocol tracing. |
| FR-19 | S | The terminal shall support running a **script file** of commands for regression/bring-up. |

### 1.4 Mock ECU

| ID | Pri | Requirement |
|----|-----|-------------|
| FR-20 | M | A **Mock ECU** shall respond to `0x10`, `0x14`, `0x19 0x02`, `0x27`, `0x3E` over CAN (virtual or VN1610). |
| FR-21 | M | The Mock ECU shall hold a **configurable DTC table** returned for `0x19 0x02`. |
| FR-22 | M | The Mock ECU shall implement a **seed/key** exchange whose key algorithm matches the test DLL (or a documented test algorithm), so the full `0x27` flow can be validated offline. |
| FR-23 | S | The Mock ECU shall optionally **inject NRCs** (e.g. `0x78` pending, `0x35` invalidKey, `0x33` securityAccessDenied) for negative-path testing. |
| FR-24 | C | The Mock ECU shall support a software **TCP-loopback mode** (no CAN) so the protocol can be exercised with zero Vector dependency. |

### 1.5 Logging / observability

| ID | Pri | Requirement |
|----|-----|-------------|
| FR-25 | M | Every request and response shall be logged at each layer (CAPL Write window, bridge, client) with timestamp, direction, and sequence id. |
| FR-26 | S | A request shall be **traceable end-to-end** by its sequence id across client → transport → CAPL → response. |

---

## 2. Non-functional requirements

| ID | Pri | Requirement |
|----|-----|-------------|
| NFR-1 | M | **Tool-agnostic:** the same CAPL nodes and the same client builds shall run on both CANoe and CANalyzer (subject to the CAPL TCP API caveat for Option A). |
| NFR-2 | M | **No CDD:** the system shall function with only the built-in Basic Diagnostics (UDS) template; no CDD/ODX file shall be required. |
| NFR-3 | S | **Latency:** for a simple request (e.g. `19 02 FF`) against the Mock ECU on a virtual channel, round-trip client→client shall be ≤ 150 ms (excluding ECU-side processing). |
| NFR-4 | M | **Correctness:** request bytes sent on the bus shall byte-for-byte match the client-supplied request; verified against trace. |
| NFR-5 | S | **Resilience:** a malformed client line shall produce a protocol error response, never crash the CAPL node or bridge. |
| NFR-6 | S | **Portability of clients:** the Python terminal shall run on Windows, Linux, and macOS; the Flutter UI shall build for desktop (Windows primary). |
| NFR-7 | M | **Single-machine default:** transports shall bind to localhost by default; remote binding is explicit opt-in. |
| NFR-8 | S | **Maintainability:** version-sensitive CAPL (raw request syntax) shall be isolated in `flexdiag_core.can` so version ports touch one file. |
| NFR-9 | C | **Throughput:** the system shall handle at least 20 sequential requests/second through either transport against the Mock ECU. |
| NFR-10 | M | **Concurrency safety (Option B):** COM access shall be serialized on a single STA thread; no COM call shall be made from the async server thread. |

---

## 3. Environment & external constraints

### 3.1 Hardware

| ID | Requirement |
|----|-------------|
| ENV-1 | Vector **VN1610** (or compatible XL-family interface) with current Vector driver installed. |
| ENV-2 | Windows PC capable of running CANoe/CANalyzer (Vector's stated OS requirement for the installed version). |
| ENV-3 | A target: real ECU on CAN, **or** the Mock ECU on a virtual/second channel. |

### 3.2 Software

| ID | Requirement |
|----|-------------|
| ENV-4 | Vector **CANoe or CANalyzer** (pin a reference version in the setup guide; both have Basic Diagnostics + CAPL diagnostic functions). |
| ENV-5 | Vector **XL Driver Library / driver** (installed with the tool) for VN1610. |
| ENV-6 | **Seed-key DLL** following the Vector `GenerateKeyEx` convention, bitness matching the Vector process. |
| ENV-7 | **Python 3.10+** for bridge, terminal, and Mock ECU. Bridge uses `pywin32` (COM) and a WebSocket lib; Mock ECU uses `python-can` (+ `can-isotp`) when on a real/virtual bus. |
| ENV-8 | **Flutter** (stable channel) with desktop support enabled; `web_socket_channel` and `dart:io` sockets. |
| ENV-9 | For Option A, the CAPL **TCP/IP API** must be available in the installed CANalyzer/CANoe build (always on CANoe; verify on CANalyzer). |

### 3.3 Constraints / assumptions

| ID | Constraint |
|----|------------|
| ENV-10 | The Vector tool **always owns the VN1610** in this architecture; clients never call `vxlapi` directly. |
| ENV-11 | Single diagnostic target in v1; physical/response CAN IDs and addressing mode are configured once in the diagnostic layer. |
| ENV-12 | COM automation requires the Vector tool to be **running with a loaded configuration**; the bridge does not install or license the tool. |
| ENV-13 | 11-bit normal addressing assumed by default; extended/29-bit is a configuration change in the diagnostic layer, not a code change. |

---

## 4. Acceptance criteria (traceability highlights)

| Capability | Verified by |
|------------|-------------|
| Read DTC (FR-1/2) | Terminal + Flutter show decoded DTC table from Mock ECU and real ECU on both transports |
| Tester Present (FR-4) | Trace shows periodic `3E 80`; toggle start/stop works on A and B |
| Security (FR-5) | `27 01`→seed→DLL key→`27 02`→unlocked against Mock ECU (matching algo) and real ECU |
| Transport switch (FR-13/14) | Same session switches A↔B and repeats Read DTC with no code change |
| No CDD (NFR-2) | Entire flow runs with only Basic Diagnostics configured |
| Tool-agnostic (NFR-1) | All four capabilities pass on CANoe and CANalyzer |
