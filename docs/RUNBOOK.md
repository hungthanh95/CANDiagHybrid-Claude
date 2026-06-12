# RUNBOOK — Driving FlexDiag with AI agents

**Purpose:** copy-paste prompts to run the project milestone by milestone with the FlexDiag subagents, with explicit human-gates. Keep this open while working; you should rarely need to type prompts from scratch.

> Model: one milestone per turn, confirm, then advance. STATUS.md is the memory between sessions — every new session starts by reading it.

---

## 0. One-time, start of every session

Paste this first in a fresh Claude Code session so the main agent re-orients from disk, not from a remembered context:

```
You are the orchestrator for FlexDiag. Read CLAUDE.md and docs/STATUS.md first,
then tell me: which milestone we're on, what's ✅/🟡/⬜ in the capability matrix,
and the single next action. Do not start work yet — wait for my go.
```

---

## 1. Kickoff (sets the operating model)

Use once at project start, or any time you want to reset the orchestration rules:

```
You are the orchestrator for FlexDiag. Work through docs/00-MASTER-PLAN.md phasing,
one milestone at a time (M0 → M6). For each milestone:
1. Summarize its exit criteria and a short plan.
2. Delegate to the right subagent: flexdiag-developer (code), flexdiag-tester (tests),
   flexdiag-reviewer (approve every protected change), flexdiag-status (update STATUS.md).
3. Enforce CLAUDE.md §3 — especially separation of duty: the developer must NOT
   self-approve changes to the protocol, sysvar layout, flexdiag_core.can, or the
   security path. Route those through flexdiag-reviewer.
4. When a step needs a human (verify CAPL TCP API on CANalyzer, attach the seed-key DLL,
   run on VN1610 / a real ECU, or anything touching security access), STOP and ask me.
   Do not assume or fabricate hardware results.
5. At the end of each milestone, have flexdiag-status update docs/STATUS.md, then report
   status and ask for my confirmation before the next milestone.
Do not advance past one milestone per turn without my confirmation. Start with M0.
```

---

## 2. Per-milestone prompts

Run these in order, one per turn. Wait for the status report + your confirmation between each.

### M0 — Freeze the protocol
```
Proceed with M0. Have flexdiag-reviewer review the wire protocol (docs/03 §1) and the
System Variable layout (docs/03 §2) for internal consistency and the "one protocol, two
transports" rule. Resolve any findings, then freeze: confirm proto=1 in the handshake.
Have flexdiag-status mark M0 and report. Cite the doc-04 rules you enforced.
```
**Human-gate:** none (pure design). You just confirm the frozen spec reads right.

### M1 — Software loopback (mock-first)
```
Proceed with M1. Have flexdiag-developer implement, mock-first on a software TCP loopback:
mock_ecu/ (UDS responder per docs/03 §5), terminal/ (TUI + protocol parser + .flex runner),
and protocol/ (shared codec). Then have flexdiag-tester cover codec decode and the negative
paths (0x78, 0x35, 0x33, malformed line, transport drop), and run all four capabilities
over the loopback. Have flexdiag-status update the matrix. No Vector yet.
```
**Human-gate:** none (no Vector/hardware). Review the test matrix output.

### M2 — Option A live (CAPL TCP + Vector)
```
Proceed with M2. First: tell me the exact one-node CAPL compile test to verify the TCP/IP
API on my CANalyzer build (per docs/05 §7.1), and WAIT for my result. Once I confirm it's
available, have flexdiag-developer finalize flexdiag_tcp.can against flexdiag_core.can
(reviewer approves the core). Give me the step-by-step from docs/05 to wire the Vector
config + Mock ECU on a virtual channel, then the terminal commands to validate all four
capabilities over Option A. Have flexdiag-status record topology + tool.
```
**Human-gate (you do):** run the CAPL compile test; build the Vector config; start the
measurement; later repeat on VN1610 + real ECU. Report results back each time.

### M3 — Option B live (COM + sysvar bridge)
```
Proceed with M3. Have flexdiag-developer finalize bridge/ (COM on one STA thread, async
WS via queues) and flexdiag_sysvar.can. Walk me through importing the Diag sysvar namespace
(docs/05 §4) and starting the bridge. Then validate all four capabilities over Option B
with the terminal, and confirm behaviour is byte-identical to Option A. Status update.
```
**Human-gate (you do):** import the sysvar namespace; start the tool + bridge; confirm COM
automation is allowed on the machine. Anything touching security → you trigger it.

### M4 — Transport switch
```
Proceed with M4. Have flexdiag-developer implement runtime A↔B switching in the terminal
(switch behind the transport interface; no feature code changes). flexdiag-tester repeats
Read DTC after switching, both directions, and confirms identical results. Status update.
```
**Human-gate:** none beyond a real tool running for the live half.

### M5 — Flutter parity
```
Proceed with M5. Have flexdiag-developer build flutter_app/: transport behind DiagService,
pure tested codecs in codec/, screens for connect/transport-switch/session/read-DTC(decoded)/
clear-DTC/security(single action)/tester-present/log. flexdiag-tester verifies all four
capabilities on both transports from the UI. Status update.
```
**Human-gate (you do):** trigger security from the UI against a real/mock ECU; eyeball the UX.

### M6 — Harden & release
```
Proceed with M6. Have flexdiag-developer add reconnection, timeouts, NRC surfacing, and
logging polish. flexdiag-tester runs the full negative-path + byte-accuracy suite on BOTH
transports and BOTH tools (CANoe and CANalyzer). flexdiag-reviewer does a final pass on the
protected areas. Confirm docs/05 lets a fresh machine reproduce the setup. Status → M6 done.
```
**Human-gate (you do):** the CANoe-and-CANalyzer cross-check needs both tools; the
reproducibility check ideally runs on a clean machine.

---

## 3. Direct subagent calls (when you don't want the orchestrator)

```
Have flexdiag-reviewer review <paths/diff> against the protected-area rules; APPROVE or REQUEST CHANGES with numbered items.
Have flexdiag-developer implement <thing> per docs/03 §<n>, mock-first; do not touch protected areas without review.
Have flexdiag-tester run the negative-path suite (0x78/0x35/0x33) against the Mock ECU on both transports and report a pass/fail matrix.
Have flexdiag-status refresh docs/STATUS.md from the latest results and summarize what changed.
```

---

## 4. Human-gate checklist (the things agents cannot do for you)

| Gate | When | You must |
|------|------|----------|
| **CAPL TCP/IP API check** | Start of M2 | Compile a one-node `TcpListen` test; report available/not. If not → Option B only. |
| **Vector config build** | M2 / M3 | Create the measurement: channel map, Basic Diagnostics `ECU1`, IDs, sysvar namespace (docs/05). |
| **Seed-key DLL** | Before any `0x27` | Attach the DLL (bitness = tool process); keep it out of git. |
| **Security access run** | Any `0x27` test | You trigger it explicitly; never let an agent auto-unlock. |
| **Real hardware** | VN1610 + real ECU | Connect, set baud/IDs, run; report bus behaviour / trace back. |
| **Both-tools cross-check** | M6 | Repeat the suite on CANoe and CANalyzer. |

---

## 5. Guardrails (keep the agents on-plan)

- **One milestone per turn**, end with a STATUS.md update + your confirmation. This is the main control against drift.
- **STATUS.md is the memory.** New session → read it, resume the open milestone. Don't rely on context retention.
- **Make them cite rules.** Add "cite the CLAUDE.md / doc-04 rule you're enforcing" to keep decisions anchored.
- **Never fabricate hardware results.** If an agent reports a bus/ECU/security result you didn't actually run, that's a red flag — reject and re-run for real.
- **Mock-first is leverage.** M0, M1, and most of M4/M5 logic run fully offline — agents handle those nearly end-to-end. M2, M3, and every security step are where you sit in the loop. That split is by design, not a limitation.
