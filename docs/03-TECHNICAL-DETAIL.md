# Technical Detail — FlexDiag

**Document:** Technical Detail
**Status:** Draft v1.0

This document specifies the wire protocol, the System Variable layout, the CAPL backend, the Python bridge, the Mock ECU, and the client-side codecs. It is the implementation contract; freeze it (M0) before building dependent components.

---

## 1. Wire protocol (shared by Option A and Option B)

**Frozen at `proto=1`** as of M0 — see `docs/STATUS.md` §1.

### 1.1 Design

A **line-based, ASCII** protocol. One message per line, terminated by `\n`. Fields are space-separated. Hex bytes are uppercase, no `0x`, space-separated. This keeps CAPL parsing trivial (CAPL JSON parsing is painful) and is human-readable in logs and in the terminal.

```
<SEQ> <VERB> [args...]\n
```

- `SEQ` — client-generated decimal correlation id (monotonic per connection). Responses echo it. `0` is reserved for unsolicited/async events.
- `VERB` — command or response keyword (below).
- `args` — verb-specific.

### 1.2 Client → server commands

| Verb | Args | Meaning |
|------|------|---------|
| `HELLO` | `proto=1` | Optional handshake; if sent, server replies `<seq> READY ...` echoing seq. |
| `SESSION` | `<session_hex>` | `0x10 <session>` e.g. `SESSION 03`. |
| `READDTC` | `[mask_hex]` | `0x19 02 <mask>`; default mask `FF`. |
| `CLEARDTC` | — | `0x14 FF FF FF` (full clear; group selection out of scope for v1). |
| `SECURITY` | `<level_hex>` | Full seed/key unlock at odd level, e.g. `SECURITY 01`. |
| `TP` | `START` \| `STOP` | Periodic tester present. |
| `RAW` | `<byte> <byte> ...` | Send arbitrary UDS request bytes. |
| `PING` | — | Liveness; server replies `PONG`. |
| `BYE` | — | Graceful close. |

### 1.3 Server → client responses

| Verb | Args | Meaning |
|------|------|---------|
| `READY` | `proto=1 tool=<CANoe\|CANalyzer> transport=<A\|B>` | Handshake ack. Sent unsolicited as `0 READY proto=1 tool=<CANoe\|CANalyzer> transport=<A\|B>` immediately on connect (both transports); also sent as `<seq> READY ...` if the client sends `HELLO`. |
| `RSP` | `<byte> <byte> ...` | Positive UDS response (full bytes incl. SID+0x40). |
| `NRC` | `<sid_hex> <nrc_hex>` | Negative response `7F <sid> <nrc>`. |
| `OK` | `<what>` | Non-UDS success. The only two v1 forms are `OK TP` (terminal response to both `TP START` and `TP STOP`; seq correlation tells the client which) and `OK SEC <level_hex>` (terminal response to a successful `SECURITY <level_hex>` unlock, where `<level_hex>` is the odd level that was requested, 2 uppercase hex digits, e.g. `OK SEC 01`). |
| `ERR` | `<code> <text>` | Protocol/tool error (not an ECU NRC). |
| `EVT` | `<name> [args]` | Reserved for future async notifications. No `EVT` messages are defined in `proto=1`. |
| `PONG` | — | Liveness ack. |

`SESSION` responses use `RSP` like `READDTC`/`RAW` (positive UDS bytes), never `OK`.

### 1.4 Examples

```
12 READDTC FF
12 RSP 59 02 FF 00 12 34 2F 00 56 78 08
        │  │  │  └─ DTC#1: 00 12 34 status 2F │ DTC#2: 00 56 78 status 08
        │  │  └─ availabilityMask
        │  └─ subfunction echo
        └─ 0x19+0x40

13 SECURITY 01
13 OK SEC 01                # success
# or
13 NRC 27 35                # invalidKey

14 RAW 22 F1 90
14 RSP 62 F1 90 56 49 4E ...   # ReadDataByIdentifier VIN, decoded client-side

15 TP START
15 OK TP

16 SESSION 03
16 RSP 50 03 00 32 01 F4
```

### 1.5 Rules

- Server **must** echo the request `SEQ` on its terminal response (`RSP`/`NRC`/`OK`/`ERR`).
- A command yields exactly **one** terminal response (plus optional `EVT` lines at seq `0`).
- Bytes are always **full UDS frames** at the protocol boundary (the client builds SIDs; the server forwards raw). This keeps the server dumb and the client authoritative.
- Lines (including `RAW` byte payloads) are capped at `kMaxLen` = 4095 bytes (§3.1). A request that would exceed this is rejected with `ERR 422 bad_args` before dispatch.

`ERR` codes are a closed set in `proto=1`:

| Code | Text | Meaning |
|------|------|---------|
| 400 | `unknown_verb` | Verb not recognized |
| 422 | `bad_args` | Malformed hex/length/args, or line exceeds max length |
| 500 | `keygen_fail` | Seed-key DLL `diagGenerateKeyFromSeed` failed during SECURITY |
| 503 | `tool_unavailable` | CANoe/CANalyzer COM/tool not reachable |
| 504 | `ecu_timeout` | No ECU response within the diagnostic timeout |

---

## 2. System Variable layout (Option B)

Namespace `Diag`. The bridge writes the request and bumps a trigger; CAPL reacts, runs the diagnostic, and writes the response and bumps a response counter; the bridge listens for that counter changing.

| Sysvar | Type | Writer | Purpose |
|--------|------|--------|---------|
| `Diag::ReqData` | Data (byte array) | bridge | Raw request bytes (full UDS frame). |
| `Diag::ReqSeq` | Int | bridge | Correlation id; written before `ReqTrigger`. |
| `Diag::ReqKind` | Int | bridge | 0=RAW, 1=READDTC, 2=CLEARDTC, 3=SECURITY, 4=SESSION, 5=TP_START, 6=TP_STOP. |
| `Diag::ReqArg` | Int | bridge | Generic arg (e.g. security level, session id, mask). |
| `Diag::ReqTrigger` | Int | bridge | Incremented to fire the request (CAPL reacts on change). |
| `Diag::RspData` | Data (byte array) | CAPL | Raw response bytes (positive or `7F..`). |
| `Diag::RspSeq` | Int | CAPL | Echoed correlation id. |
| `Diag::RspStatus` | Int | CAPL | 0=positive, 1=negative(NRC), 2=ok(non-UDS), 3=error. |
| `Diag::RspKind` | Int | CAPL | Echoes the `ReqKind` (same 0–6 enum) of the operation this response belongs to. Lets the bridge format `OK TP` / `OK SEC <level>` without per-seq state. |
| `Diag::RspTrigger` | Int | CAPL | Incremented when a response is ready (bridge reacts on change). |

> Why both `ReqData` and `ReqKind/ReqArg`? `RAW` uses `ReqData` directly. Higher-level verbs (`READDTC`, `SECURITY`, …) use `ReqKind`+`ReqArg` so CAPL runs the multi-step logic (e.g. security seed/key) rather than the bridge pre-building frames. This keeps the seed/key dance and tester-present timing inside the tool.

> `PING`, `BYE`, and `HELLO` are handled entirely by the transport layer (TCP node / Python bridge) and never reach `flexdiag_core.can` or `Diag::Req*`. The `ReqKind` enum (0–6) covers only operations forwarded to the diagnostic core.

> `Diag::ReqData`/`Diag::RspData` are CANoe/CANalyzer System Variables of type **Data** (variable-length byte array, max `kMaxLen`=4095 bytes per §3.1). Via COM, `.Value` reads as a tuple of ints 0–255 (bridge: `bytes(sv('RspData').Value)`); writes accept a sequence of ints 0–255 (bridge: `sv('ReqData').Value = tuple(data)`).

Define these in a `.vsysvar` file imported in the setup guide.

---

## 3. CAPL backend

### 3.1 `flexdiag_core.can` — diagnostic primitives (transport-agnostic)

This is the only file touching the diagnostic layer. Transport nodes call its functions and consume its callback via a shared response buffer + a `PublishResponse()` hook that each transport implements.

```c
/* flexdiag_core.can — shared diagnostic primitives.
 * Version-sensitive raw-request syntax is isolated here.
 * Target qualifier "ECU1" must match the Basic Diagnostics ECU name.
 */
variables
{
  const dword kMaxLen = 4095;
  byte  gReq[4095];
  byte  gRsp[4095];
  dword gReqSeq;          // current correlation id
  int   gReqKind;         // current operation kind (0-6, same enum as Diag::ReqKind)
  // gReqSeq/gReqKind are single-slot globals: FlexDiag v1 assumes one outstanding
  // diagnostic request at a time per connection; a future concurrent-request design
  // would need per-seq state instead.
}

/* ---- Transport hook: each transport node defines these ---- */
//   void PublishRsp(dword seq, int status, byte data[], dword len, int kind);
//     status: 0 positive, 1 negative, 2 ok, 3 error
//     kind:   echoes the ReqKind (0-6) of the operation this response belongs to
// They are declared here as 'export' contracts; transport nodes implement.

on start
{
  diagSetTarget("ECU1");   // REQUIRED, especially on CANalyzer
  write("FlexDiag core started, target ECU1");
}

/* Build + send a raw UDS request from a byte buffer. */
void SendRaw(dword seq, byte data[], dword len)
{
  diagRequest ECU1.* req;           // wildcard / generic request object
  gReqSeq = seq;
  diagResize(req, len);
  diagSetPrimitiveData(req, data, len);
  diagSendRequest(req);
}

/* Single response handler for the ECU1 diagnostic object. */
on diagResponse ECU1.*
{
  long len;
  len = diagGetPrimitiveSize(this);
  if (len > kMaxLen) len = kMaxLen;
  diagGetPrimitiveData(this, gRsp, len);

  if (diagIsNegativeResponse(this))
    PublishRsp(gReqSeq, 1, gRsp, len, gReqKind);   // 7F <sid> <nrc>
  else
    PublishRsp(gReqSeq, 0, gRsp, len, gReqKind);
}

/* ---- High-level helpers ---- */
/* Each Do* helper sets gReqKind so PublishRsp() can echo it (Diag::RspKind).
 * The TP helpers (kind 5/6) are dispatched directly by the transports, which
 * call PublishRsp(seq,2,buf,0,5) / PublishRsp(seq,2,buf,0,6) themselves. */

void DoSession(dword seq, byte session)
{
  byte r[2];
  gReqKind = 4;
  r[0] = 0x10; r[1] = session;
  SendRaw(seq, r, 2);
}

void DoReadDtc(dword seq, byte mask)
{
  byte r[3];
  gReqKind = 1;
  r[0] = 0x19; r[1] = 0x02; r[2] = mask;
  SendRaw(seq, r, 3);
}

void DoClearDtc(dword seq, byte g0, byte g1, byte g2)
{
  byte r[4];
  gReqKind = 2;
  r[0] = 0x14; r[1] = g0; r[2] = g1; r[3] = g2;
  SendRaw(seq, r, 4);
}

/* Security: request seed (odd level). The key step happens when the
 * seed response arrives — see SecurityOnResponse(). */
void DoSecuritySeed(dword seq, byte level)
{
  byte r[2];
  gReqKind = 3;
  r[0] = 0x27; r[1] = level;          // odd level => requestSeed
  SendRaw(seq, r, 2);
}

/* Called from the response handler when a 67 <oddLevel> seed arrives.
 * Generates the key via the attached seed-key DLL and sends 27 <evenLevel> key. */
void SecuritySendKey(dword seq, byte oddLevel, byte seed[], dword seedLen)
{
  byte  key[256];
  byte  req[258];
  dword keyLen, i;
  long  ret;

  gReqKind = 3;
  ret = diagGenerateKeyFromSeed(seed, seedLen, oddLevel, "", 0,
                                key, elcount(key), keyLen);
  if (ret != 0) { PublishRsp(seq, 3, gRsp, 0, gReqKind); return; }  // KEYGEN_FAIL

  req[0] = 0x27;
  req[1] = oddLevel + 1;              // sendKey = odd+1 (even)
  for (i = 0; i < keyLen; i++) req[i + 2] = key[i];
  SendRaw(seq, req, keyLen + 2);
}

void DoTesterPresent(int enable)
{
  if (enable) diagStartTesterPresent();  // tool emits 3E 80 at configured period
  else        diagStopTesterPresent();
}
```

> **Security flow nuance.** Because security is two round-trips, the transport node tracks "this seq is a SECURITY op at level L". When `on diagResponse` fires and the data starts `67 L` (seed), the node calls `SecuritySendKey()`. When the data starts `67 (L+1)`, it reports `OK SEC L`. A small state variable (current security seq + level) in the core or transport node carries this. Negative responses at either step are reported as `NRC`.

### 3.2 `flexdiag_tcp.can` — Option A transport

```c
/* flexdiag_tcp.can — TCP server transport (Option A).
 * Requires CAPL TCP/IP API (verify availability on CANalyzer build).
 */
includes { /* may include a small TCP/IP header per Vector docs */ }

variables
{
  dword gSocket;
  dword gClient;
  char  gRxLine[512];
  const int kPort = 9000;
  // security state
  dword gSecSeq; byte gSecLevel; int gSecActive;
}

on start
{
  // Open + listen (exact calls per Vector TCP/IP API in the installed version)
  TcpOpen(gSocket, ...);
  TcpBind(gSocket, INADDR_ANY, kPort);
  TcpListen(gSocket);
  write("FlexDiag TCP listening on %d", kPort);
}

// On accepted connection, send the unsolicited banner immediately:
//   TcpSendLine(0, "READY proto=1 tool=... transport=A")   // "0 READY ..."

// On received data → parse one line → dispatch
on TcpReceive
{
  // read into gRxLine, split on space, switch on VERB:
  //   HELLO    -> reply "<seq> READY proto=1 tool=... transport=A" (echoes seq;
  //               the unsolicited "0 READY ..." banner was already sent on accept)
  //   SESSION  -> DoSession(seq, arg)
  //   READDTC  -> DoReadDtc(seq, mask)
  //   CLEARDTC -> DoClearDtc(seq, 0xFF,0xFF,0xFF)   // v1: group fixed to FF FF FF (full clear)
  //   SECURITY -> gSecActive=1; gSecSeq=seq; gSecLevel=arg; DoSecuritySeed(seq, arg)
  //   TP START -> DoTesterPresent(1); PublishRsp(seq,2,buf,0,5)   // -> "OK TP"
  //   TP STOP  -> DoTesterPresent(0); PublishRsp(seq,2,buf,0,6)   // -> "OK TP"
  //   RAW      -> gReqKind = 0; SendRaw(seq, bytes, len)   // set kind at dispatch, not inside SendRaw
  //   PING     -> reply "<seq> PONG"
}

/* Implements the core's transport hook. */
void PublishRsp(dword seq, int status, byte data[], dword len, int kind)
{
  char line[2048];
  // Security continuation: a positive 67 seed -> generate+send key, do not emit yet
  if (gSecActive && status == 0 && len >= 2 && data[0] == 0x67)
  {
    if (data[1] == gSecLevel) {                 // seed arrived
      SecuritySendKey(seq, gSecLevel, /*seed*/ &data[2], len - 2);
      return;                                   // wait for key response
    }
    if (data[1] == gSecLevel + 1) {             // unlocked
      gSecActive = 0;
      TcpSendLine(seq, "OK SEC %02X", gSecLevel);  // gSecLevel = odd level requested
      return;
    }
  }
  // Normal mapping
  switch (status) {
    case 0: TcpSendBytesLine(seq, "RSP", data, len); break;
    case 1: TcpSendNrc(seq, data, len); break;      // 7F sid nrc
    case 2:
      if (kind == 5 || kind == 6) TcpSendLine(seq, "OK TP");
      break;
    case 3: TcpSendLine(seq, "ERR 500 keygen_fail"); gSecActive=0; break;
  }
}
```

### 3.3 `flexdiag_sysvar.can` — Option B transport

```c
/* flexdiag_sysvar.can — System Variable transport (Option B).
 * Driven by the Python COM bridge writing Diag::Req* and bumping Diag::ReqTrigger.
 */
variables { dword gSecSeq; byte gSecLevel; int gSecActive; }

on sysvar Diag::ReqTrigger
{
  dword seq = @Diag::ReqSeq;
  int   kind = @Diag::ReqKind;
  int   arg  = @Diag::ReqArg;
  byte  buf[4095]; dword len;

  switch (kind) {
    case 0: // RAW
      len = sysGetVariableData(...Diag::ReqData..., buf);
      gReqKind = 0;          // set at dispatch, not inside SendRaw (would clobber gReqKind=3
                              // set by SecuritySendKey() just before its own SendRaw call)
      SendRaw(seq, buf, len);
      break;
    case 1: DoReadDtc(seq, (byte)arg); break;          // arg = mask
    case 2: DoClearDtc(seq, 0xFF,0xFF,0xFF); break;     // v1: group fixed to FF FF FF (full clear); no other call is sanctioned
    case 3: gSecActive=1; gSecSeq=seq; gSecLevel=(byte)arg;
            DoSecuritySeed(seq,(byte)arg); break;
    case 4: DoSession(seq,(byte)arg); break;
    case 5: DoTesterPresent(1); PublishRsp(seq,2,buf,0,5); break;
    case 6: DoTesterPresent(0); PublishRsp(seq,2,buf,0,6); break;
  }
}

/* Implements the core's transport hook by writing response sysvars. */
void PublishRsp(dword seq, int status, byte data[], dword len, int kind)
{
  // Security continuation identical to TCP node:
  if (gSecActive && status==0 && len>=2 && data[0]==0x67) {
    if (data[1]==gSecLevel) { SecuritySendKey(seq,gSecLevel,&data[2],len-2); return; }
    if (data[1]==gSecLevel+1){ gSecActive=0; status=2; /* OK SEC */ }
  }
  sysSetVariableData(...Diag::RspData..., data, len);
  @Diag::RspSeq    = seq;
  @Diag::RspStatus = status;
  @Diag::RspKind   = kind;
  @Diag::RspTrigger = @Diag::RspTrigger + 1;   // notify bridge
}
```

> Exact sysvar data get/set CAPL calls (`sysGetVariableData` / `sysSetVariableData` / the `@` accessor for scalars) vary slightly by tool version; isolate them and confirm against the installed Help.

---

## 4. Python bridge (Option B)

Responsibilities: WebSocket server for clients; COM client on a dedicated **STA** thread; translate protocol lines ↔ sysvar writes/events; auto-detect CANoe vs CANalyzer.

### 4.1 Structure

```python
# bridge/flexdiag_bridge.py  (sketch)
import threading, queue, asyncio, pythoncom
import win32com.client
import websockets

class VectorCom:
    """Runs entirely on one STA thread; owns the COM app + sysvars."""
    def __init__(self, prefer="auto"):
        self.cmd_q  = queue.Queue()     # (seq, kind, arg, data) from clients
        self.evt_q  = queue.Queue()     # (seq, status, kind, data) to clients
        self._req_arg = {}              # seq -> arg, for OK SEC <level> formatting (see §4.2)
        self._stop  = threading.Event()
        self.thread = threading.Thread(target=self._run, args=(prefer,), daemon=True)

    def start(self): self.thread.start()

    def _connect(self, prefer):
        for prog_id in (["CANoe.Application","CANalyzer.Application"]
                        if prefer=="auto" else [f"{prefer}.Application"]):
            try:
                return win32com.client.Dispatch(prog_id), prog_id.split('.')[0]
            except Exception:
                continue
        raise RuntimeError("No CANoe/CANalyzer COM server")

    def _run(self, prefer):
        pythoncom.CoInitialize()                 # STA
        app, tool = self._connect(prefer)
        self.tool = tool
        sysns = app.System.Namespaces.Item("Diag")
        def sv(name): return sysns.Variables.Item(name)

        # subscribe to RspTrigger via COM events OR poll its value
        last_rsp = sv("RspTrigger").Value
        while not self._stop.is_set():
            pythoncom.PumpWaitingMessages()      # required for COM events
            # 1) push any pending client command into sysvars
            try:
                seq, kind, arg, data = self.cmd_q.get_nowait()
                if data is not None: sv("ReqData").Value = data    # byte array
                sv("ReqSeq").Value  = seq
                sv("ReqKind").Value = kind
                sv("ReqArg").Value  = arg
                self._req_arg[seq] = arg            # for OK SEC <level> formatting (§4.2)
                sv("ReqTrigger").Value = sv("ReqTrigger").Value + 1
            except queue.Empty:
                pass
            # 2) detect a new response
            cur = sv("RspTrigger").Value
            if cur != last_rsp:
                last_rsp = cur
                self.evt_q.put((int(sv("RspSeq").Value),
                                int(sv("RspStatus").Value),
                                int(sv("RspKind").Value),
                                bytes(sv("RspData").Value)))
        pythoncom.CoUninitialize()
```

```python
# WebSocket side (asyncio) bridges text protocol <-> cmd_q / evt_q
async def handle(ws, vec):
    await ws.send(f"0 READY proto=1 tool={vec.tool} transport=B")
    async def pump_events():
        loop = asyncio.get_event_loop()
        while True:
            seq, status, kind, data = await loop.run_in_executor(None, vec.evt_q.get)
            await ws.send(encode_response(seq, status, kind, data, vec._req_arg.pop(seq, None)))
    asyncio.create_task(pump_events())
    async for line in ws:
        seq, kind, arg, data = parse_command(line)   # maps verbs -> sysvar kinds
        if kind == HELLO:                            # handled here, never reaches sysvars
            await ws.send(f"{seq} READY proto=1 tool={vec.tool} transport=B")
            continue
        vec.cmd_q.put((seq, kind, arg, data))
```

### 4.2 Notes

- COM events (`OnVariableChanged`) can replace polling `RspTrigger`; polling with `PumpWaitingMessages` is simpler and robust for v1. Keep the poll interval small (a few ms) for responsiveness.
- Never call `Dispatch`/sysvar from the asyncio thread — only via `cmd_q`. This satisfies NFR-10.
- `prefer` lets the operator force `CANoe` or `CANalyzer`; `auto` tries CANoe first.
- The unsolicited `0 READY proto=1 tool=... transport=B` banner above is sent on connect for both transports; if the client sends `HELLO`, the bridge replies `<seq> READY ...` directly (handled entirely by the bridge, like `PING`/`BYE` — see §2's note on `ReqKind`).
- Formatting `OK SEC <level>` and `OK TP` is response *formatting*, not diagnostic logic: the bridge reads `(RspStatus, RspKind)` from sysvars plus the `ReqArg` (security level) it itself sent for that `seq`, and renders the literal text. This does not violate "diagnostics live in CAPL, never in COM" (CLAUDE.md §3 rule 4) because no UDS request/response bytes are interpreted — only the non-UDS `OK` line is composed.
- `encode_response` needs the security level for `OK SEC <level_hex>` (when `kind == 3 and status == 2`), but that level isn't in the `(seq, status, kind, data)` 4-tuple from `evt_q`. `VectorCom` keeps a small per-seq dict `self._req_arg` populated when the command is sent (`self._req_arg[seq] = arg`); the caller pops `self._req_arg.pop(seq, None)` for the matching `seq` and passes it to `encode_response` to render `<level_hex>`.

---

## 5. Mock ECU

A Python UDS responder. Two modes: **CAN mode** (virtual or VN1610 via `python-can` + `can-isotp`) and **TCP-loopback mode** (speaks the *bus side* over a simple socket for the all-software topology).

```python
# mock_ecu/mock_ecu.py (sketch, CAN mode)
import isotp, can

DTCS = [  # (3-byte DTC, status)
    (0x001234, 0x2F),
    (0x005678, 0x08),
]
SEED = bytes([0x11,0x22,0x33,0x44])
def test_key(seed, level):       # must match the test DLL / documented algo
    return bytes((b ^ 0x5A) for b in seed)

session = 0x01
unlocked = False
pending_seed_level = None

def handle(req: bytes) -> bytes | None:
    global session, unlocked, pending_seed_level
    sid = req[0]
    if sid == 0x10:                                   # session control
        session = req[1]; return bytes([0x50, req[1], 0x00,0x32,0x01,0xF4])
    if sid == 0x3E:                                   # tester present
        return None if (len(req)>1 and req[1]&0x80) else bytes([0x7E,0x00])
    if sid == 0x19 and req[1] == 0x02:                # read DTC by status mask
        mask = req[2]; out = bytearray([0x59,0x02,0xFF])
        for dtc,st in DTCS:
            if st & mask:
                out += bytes([(dtc>>16)&0xFF,(dtc>>8)&0xFF,dtc&0xFF, st])
        return bytes(out)
    if sid == 0x14:                                   # clear
        return bytes([0x54])
    if sid == 0x27:                                   # security access
        lvl = req[1]
        if lvl % 2 == 1:                              # request seed
            pending_seed_level = lvl
            return bytes([0x67, lvl]) + SEED
        else:                                         # send key
            exp = test_key(SEED, pending_seed_level)
            if bytes(req[2:]) == exp:
                unlocked = True; return bytes([0x67, lvl])
            return bytes([0x7F, 0x27, 0x35])          # invalidKey
    return bytes([0x7F, sid, 0x11])                   # serviceNotSupported
```

- Wire the handler under an ISO-TP stack bound to RX `0x7E0` / TX `0x7E8` (configurable).
- **NRC injection (FR-23):** a config flag can force `0x78` (respond pending then final) or `0x33`/`0x35` for negative-path tests.
- The mock's key algorithm must equal whatever the **test** DLL does, so the offline security flow passes; against the real ECU the real DLL is used inside CAPL.

---

## 6. Client-side codecs (Dart + Python)

The clients own all symbolic interpretation (no CDD). Two codecs matter:

### 6.1 DTC decode (from `59 02` payload)

```
payload: 59 02 <availabilityMask> [<b2><b1><b0><status>]...
```

Decode each 4-byte record:

- 3 DTC bytes → 24-bit value.
- Top 2 bits of `b2` select the letter: `00→P (Powertrain)`, `01→C (Chassis)`, `10→B (Body)`, `11→U (Network)`.
- Remaining 22 bits → 5 hex/decimal digits per ISO 15031-6 (e.g. `0x001234` → `P0123-4` style; render as `P` + nibble layout).
- `status` byte → bitfield (testFailed, confirmedDTC, etc. per ISO 14229 DTCStatusMask). Show as flags.

```dart
// flutter_app/lib/codec/dtc.dart (sketch)
String decodeDtc(int b2, int b1, int b0) {
  const letters = ['P','C','B','U'];
  final letter = letters[(b2 >> 6) & 0x03];
  final d1 = (b2 >> 4) & 0x03;
  final rest = ((b2 & 0x3F) << 16) | (b1 << 8) | b0; // 22 bits
  return '$letter$d1${rest.toRadixString(16).toUpperCase().padLeft(4,'0')}';
}
```

### 6.2 Service builders / NRC names

Each client keeps a tiny table mapping SIDs and NRCs to names for display only:

```
NRC: 0x10 generalReject, 0x11 serviceNotSupported, 0x22 conditionsNotCorrect,
     0x31 requestOutOfRange, 0x33 securityAccessDenied, 0x35 invalidKey,
     0x36 exceedNumberOfAttempts, 0x37 requiredTimeDelayNotExpired,
     0x78 responsePending, 0x7E subFunctionNotSupportedInActiveSession ...
```

---

## 7. Flutter client (shape)

```
flutter_app/lib/
├── transport/
│   ├── transport.dart          # interface: connect/send/stream/dispose
│   ├── tcp_transport.dart      # Option A (dart:io Socket, line framing)
│   └── ws_transport.dart       # Option B (web_socket_channel)
├── protocol/
│   ├── codec.dart              # encode commands / parse responses
│   └── seq.dart                # correlation id allocator
├── codec/dtc.dart              # DTC decode
├── services/diag_service.dart  # high-level ops: readDtc(), security(), tp()
├── state/                      # app state (active transport, log, dtc list)
└── ui/                         # screens + transport switch + log view
```

`DiagService` exposes `Future<List<Dtc>> readDtc()`, `Future<bool> securityUnlock(int level)`, `void testerPresent(bool on)`, `Future<List<int>> raw(List<int> bytes)`. Switching transport rebuilds the `Transport` behind `DiagService`; the screens never know which is active.

---

## 8. Python terminal client (shape)

```
terminal/
├── transport_tcp.py            # Option A
├── transport_ws.py             # Option B
├── protocol.py                 # shared encode/parse + seq
├── repl.py                     # interactive commands (readdtc, sec 01, tp on, raw ..)
└── script.py                   # run a .flex script of commands
```

REPL commands map 1:1 to protocol verbs plus conveniences (`switch A|B`, `connect`, `trace on`). It is the reference client: if a capability works here against the Mock ECU, the Flutter UI only needs UI work.

---

## 9. End-to-end sequence (security, Option B)

```
Flutter ──"23 SECURITY 01"──► WS ──► bridge.cmd_q
bridge ─► sysvars: ReqSeq=23 ReqKind=3 ReqArg=1 ReqTrigger++
CAPL on sysvar ─► DoSecuritySeed(23,0x01) ─► diag 27 01 ─► ECU
ECU ─► 67 01 <seed> ─► on diagResponse ─► PublishRsp(0,seed)
  CAPL: gSecActive ─► SecuritySendKey ─► diagGenerateKeyFromSeed(DLL) ─► 27 02 <key>
ECU ─► 67 02 ─► on diagResponse ─► PublishRsp ─► status=2 (OK SEC) ─► RspTrigger++
bridge poll ─► RspSeq=23 status=2 ─► WS "23 OK SEC 01"
Flutter ─► shows "Unlocked (level 01)"
```

The same exchange over Option A replaces the sysvar hops with TCP line I/O; CAPL core logic is identical.
