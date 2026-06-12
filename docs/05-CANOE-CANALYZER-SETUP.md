# Setup Guide — CANoe / CANalyzer for FlexDiag

**Document:** Setup Guide
**Status:** Draft v1.0
**Audience:** Integrators setting up the Vector side from scratch.

> Menu paths and exact CAPL call names vary by tool version. Where this guide says *"(verify in Help for your version)"*, confirm against your installed CANoe/CANalyzer Help. Pin the version you used at the top of your copy of this file.

**Reference version used:** `CANalyzer 16/17` (operator-confirmed)

---

## 0. What you'll end up with

- A measurement configuration (CANoe `.cfg` or CANalyzer `.cfg`) with:
  - VN1610 channel mapped.
  - A **Basic Diagnostics (UDS)** description named **`ECU1`** (no CDD).
  - A **`Diag` System Variable** namespace.
  - The **seed-key DLL** attached (for security access).
  - The FlexDiag CAPL nodes added to the measurement.
- Verified `19 02 FF` and `27` flows against the Mock ECU or a real ECU.

---

## 1. Prerequisites

1. CANoe **or** CANalyzer installed, with the Vector driver (XL Driver Library) present.
2. VN1610 connected; visible in **Vector Hardware Configuration**.
3. Your **seed-key DLL** (`GenerateKeyEx` convention). **Bitness must match the tool process** (64-bit tool → 64-bit DLL).
4. The FlexDiag CAPL files: `flexdiag_core.can`, `flexdiag_sysvar.can`.
5. The sysvar definition file [`vector/capl/flexdiag.vsysvar`](../vector/capl/flexdiag.vsysvar) (or create the namespace manually, §4).

---

## 1.5 Pre-flight checklist (Windows, first run of §8)

Work through this once, before starting the §8 bring-up checklist, on the
machine that will run CANoe/CANalyzer. Each item references the open risk
(`docs/STATUS.md` §5) it closes.

- [x] **Python environment ready:** from the repo root, `pip install -e .[dev]`
      gets `websockets`, `pytest`, `ruff`, `black`, etc. for the terminal,
      Mock ECU, and protocol/codec tests.
- [x] **Option B COM dependency:** for the real `VectorCom` backend (not
      `--fake`), also `pip install -e .[vector]` (installs `pywin32` on
      Windows). Not needed for mock-first testing (`bridge --fake`).
- [x] **Tool version confirmed:** CANoe/CANalyzer version installed is the
      reference version at the top of this doc (`CANalyzer 16/17`) or newer.
      If different, expect to re-verify CAPL syntax (R4) — see §10
      troubleshooting.
- [ ] **Seed-key DLL bitness matches the tool process** (R3): confirm your
      attached seed-key DLL's bitness (32/64-bit) matches the CANoe/CANalyzer
      process bitness (§5 step 3).
- [ ] **Mock ECU key algorithm matches the test DLL** (R6): before step 6 of
      §8, confirm `mock_ecu.uds.Ecu.test_key` (`key[i] = seed[i] ^ 0x5A`)
      matches the algorithm implemented by the attached test seed-key DLL. If
      they differ, `27 02` will fail with `7F 27 35` (invalidKey) against the
      Mock ECU even though the DLL itself is fine.
- [x] **COM automation permitted** (Option B only): confirm
      `Dispatch("CANoe.Application")` / `Dispatch("CANalyzer.Application")` is
      not blocked by Windows/group policy on this machine — required for
      `bridge/` (R2). Quick check: with the tool running and a config loaded,
      `python -m bridge --prefer auto --port 8770` should report the detected
      tool, not a COM error.
- [ ] **VN1610 channel assignment confirmed** (R5): open **Vector Hardware
      Configuration** and confirm the VN1610's CAN channels are visible and
      assigned as expected, before proceeding to §2.
- [ ] **`flexdiag.vsysvar` ready** (Option B only): have
      [`vector/capl/flexdiag.vsysvar`](../vector/capl/flexdiag.vsysvar) on
      hand to import per §4.1 (fallback: create the `Diag` namespace manually
      per §4.2).

---

## 2. Vector Hardware Configuration (VN1610)

1. Open **Vector Hardware Configuration** (from the tool: *Hardware → … (verify in Help)*, or the standalone applet).
2. Confirm the **VN1610** appears and its **CAN channels** are listed.
3. Note which **application** the channels are assigned to. To let CANalyzer run passively alongside the tool that owns diagnostics, assign the same physical channel to both applications (multi-application access). For the basic setup, assigning channel 1 to your tool's application is enough.
4. In the tool, map **measurement channel 1 → VN1610 CAN channel 1** (verify in Help: *Network Hardware / Channel mapping*).

**Bus parameters:** set the **baud rate** to match your ECU (commonly 500 kbit/s). For CAN FD, set arbitration + data rates accordingly.

---

## 3. Diagnostic layer — Basic Diagnostics (UDS), no CDD

This is the key step that avoids needing a CDD.

1. Open the **Diagnostics/ISO TP Configuration** (CANoe: *Diagnostics → Diagnostic/ISO TP Configuration*; CANalyzer: the equivalent diagnostics configuration — *verify in Help*).
2. **Add a diagnostic description** for the target ECU. When prompted for a description source, choose the built-in **Basic Diagnostics / UDS template** (not a CDD/ODX file).
3. Set the **ECU qualifier to `ECU1`** (the CAPL uses this name; it must match exactly).
4. Configure the **transport (ISO-TP) parameters**:
   - **Addressing:** Normal, 11-bit (default for v1).
   - **Request ID (physical):** `0x7E0` (default; change to your ECU).
   - **Response ID:** `0x7E8` (default; change to your ECU).
   - **Padding:** enable, pad byte `0x00` (typical) — match your ECU.
   - **Timing:** P2 and P2* per your ECU (defaults from the template are usually fine to start).
5. Assign the diagnostic description to **measurement channel 1** (the VN1610 channel from §2).
6. Apply/close. You should now be able to open the **Diagnostic Console** for `ECU1` and send a raw request manually as a smoke test (e.g. `19 02 FF`).

> If your tool exposes a "Tester present" setting in this layer, set the **period** here (e.g. 2000 ms) and **suppress positive response** on — this is what `diagStartTesterPresent()` uses.

---

## 4. System Variables — `Diag` namespace

### 4.1 Import (preferred)

1. Open **System Variables Configuration** (*Environment / System Variables — verify in Help*).
2. **Import** [`vector/capl/flexdiag.vsysvar`](../vector/capl/flexdiag.vsysvar). Confirm the `Diag` namespace contains the variables below.

   > This file is a best-effort `.vsysvar` XML reconstruction (see header comment in the file). If **File > Import** rejects it on your installed version, fall back to §4.2 and create the namespace manually — the table there is the normative definition and matches `docs/03-TECHNICAL-DETAIL.md` §2 exactly.

### 4.2 Or create manually

Create namespace **`Diag`** with:

| Variable | Type | Notes |
|----------|------|-------|
| `ReqData` | Data / byte array | size ≥ 4095 |
| `ReqSeq` | Integer (LongLong/Int) | |
| `ReqKind` | Integer | 0=RAW,1=READDTC,2=CLEARDTC,3=SECURITY,4=SESSION,5=TP_START,6=TP_STOP |
| `ReqArg` | Integer | level/session/mask |
| `ReqTrigger` | Integer | bumped to fire |
| `RspData` | Data / byte array | size ≥ 4095 |
| `RspSeq` | Integer | |
| `RspStatus` | Integer | 0=positive,1=negative(NRC),2=ok(non-UDS),3=ERR keygen_fail,4=ERR ecu_timeout |
| `RspKind` | Integer | echoes `ReqKind` |
| `RspTrigger` | Integer | bumped when response ready |

> Match the variable **types** to what the CAPL accessors expect in your version (scalar `@Diag::X` for ints; `sysGetVariableData`/`sysSetVariableData` for the Data arrays). Verify in Help.

---

## 5. Seed-Key DLL (security access)

1. In the **diagnostic layer / security settings** for `ECU1` (CANoe: within the Diagnostic configuration's *Security* / *Seed&Key* area — *verify in Help*), browse to your **seed-key DLL**.
2. Confirm the tool accepts it (it validates the `GenerateKeyEx` export).
3. **Bitness check:** if the tool reports it can't load the DLL, you almost certainly have a 32/64-bit mismatch. Use the DLL built for the same bitness as your CANoe/CANalyzer process.
4. The CAPL call `diagGenerateKeyFromSeed(...)` uses this DLL; you do **not** load it from Python.

> Keep production DLLs out of source control. Use a **test DLL** (or the documented test algorithm) for offline work with the Mock ECU, and make sure the Mock ECU's key function matches it.

---

## 6. Add the CAPL nodes

1. Open the **Measurement Setup** (CANoe) / **Configuration** (CANalyzer).
2. Add a **CAPL node** on the CAN channel hotspot (or in the appropriate functional block — *verify in Help*).
3. Attach **`flexdiag_core.can`** and **`flexdiag_sysvar.can`**.
4. **Compile** (CAPL Browser → Compile all). Fix any version-specific syntax in `flexdiag_core.can` first (raw request + sysvar accessors are the usual suspects).

---

## 7. Bridge runtime — COM + sysvar bridge

1. Ensure the **`Diag` namespace** (§4) exists and `flexdiag_sysvar.can` is compiled.
2. Start the measurement in the tool (the bridge attaches to a *running* tool).
3. Start the bridge:
   ```
   python -m bridge --prefer auto --host 127.0.0.1 --port 8770
   ```
   `--prefer auto` tries CANoe then CANalyzer; use `--prefer CANoe` or `--prefer CANalyzer` to force.

   To test the bridge/terminal/Mock-ECU loop without a real CANoe/CANalyzer (mock-first, CLAUDE.md rule 1), use `--fake` instead: `python -m bridge --fake --port 8770`.
4. The bridge log should show the detected tool and `WebSocket listening on 8770`.
5. Test: `python -m terminal --host 127.0.0.1 --port 8770`.

> **COM gotcha:** the bridge must be allowed to automate the tool. If `Dispatch("CANoe.Application")` fails, confirm the tool is running, a config is loaded, and (on locked-down machines) that COM automation isn't blocked by policy.

---

## 8. Bring-up checklist (do these in order)

1. **Measurement starts** with no CAPL compile errors.
2. **Manual Diagnostic Console:** send `19 02 FF` to `ECU1`, get a `59 02 ...` (against Mock ECU or real ECU). Confirms the diagnostic layer + channel + IDs.
3. **Option B smoke test:** bridge up, terminal over WebSocket, `HELLO` → `READY`, `READDTC FF` → `RSP 59 02 ...`.
4. **Tester present:** `TP START` → trace shows periodic `3E 80`; `TP STOP` halts it.
5. **Security:** `SECURITY 01` → trace shows `27 01` → `67 01 <seed>` → `27 02 <key>` → `67 02`; terminal shows `OK SEC 01`.
6. **Repeat the whole checklist on the other tool** (CANoe ↔ CANalyzer) before sign-off.

---

## 9. Mock ECU for offline bring-up

To run steps 2–7 without a real ECU:

1. Create a **virtual CAN channel** (or use a second VN1610 channel) and map the tool's measurement channel to it.
2. Start the Mock ECU bound to the **bus side** (RX `0x7E0`, TX `0x7E8`):
   ```
   python mock_ecu/mock_ecu.py --interface vector --channel 1 --rx 0x7E0 --tx 0x7E8
   ```
   (or `--interface virtual` for a pure software bus, matching the tool's virtual channel.)
3. Ensure the Mock ECU's **key algorithm matches your test seed-key DLL** so step 6 passes.
4. Now the diagnostic layer in the tool talks to the Mock ECU exactly as it would a real one.

---

## 10. Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| CAPL won't compile: raw request / sysvar calls | Version-specific syntax | Adjust in `flexdiag_core.can` per Help |
| Diagnostic Console `19 02 FF` times out | Wrong CAN IDs / baud / channel | Recheck §2–§3 against ECU; check trace for the request on the bus |
| Seed-key DLL won't load | 32/64-bit mismatch | Use DLL matching tool bitness |
| `27 02` → `7F 27 35` invalidKey | Mock/real key algo mismatch | Align Mock `test_key` with the DLL, or use the right DLL |
| Bridge: `Dispatch` fails | Tool not running / no config / COM blocked | Start tool + load config; check COM policy |
| Bridge: no responses | sysvar names/types mismatch, or RspTrigger not bumped | Verify §4 names/types; confirm `flexdiag_sysvar.can` compiled |
| Tester present not on bus | tester-present period/suppress not set, or `diagStartTesterPresent` not called | Set period in diag layer (§3); send `TP START` |
| Works on CANoe, not CANalyzer | COM diagnostic object assumed, or missing `diagSetTarget` | Ensure diagnostics stay in CAPL; add `diagSetTarget("ECU1")` |

---

## 11. Quick reference (defaults)

| Item | Default |
|------|---------|
| ECU qualifier | `ECU1` |
| Baud | 500 kbit/s |
| Phys request ID | `0x7E0` |
| Response ID | `0x7E8` |
| Addressing | Normal 11-bit |
| WebSocket bridge | `127.0.0.1:8770` |
| Tester-present period | 2000 ms, suppress positive |
| Security level | odd = requestSeed, even = sendKey (e.g. `01`/`02`) |
