# CLAUDE.md — FlexDiag

This file is the **operating contract** for AI agents working on FlexDiag. Claude Code loads it automatically. It defines who does what, which model plays which role, and the rules that must never be violated. Detailed specs live in `docs/`.

> **Read before acting:** `docs/00-MASTER-PLAN.md` (scope/phases), `docs/03-TECHNICAL-DETAIL.md` (the protocol contract), `docs/04-RULES-AND-CONVENTIONS.md` (normative rules). The protocol and sysvar layout are **frozen at milestone M0** — see below.

---

## 1. What this project is

A UDS (ISO 14229) diagnostic tool. A **Flutter** operator UI and a **Python terminal** test client drive **Vector CANoe/CANalyzer + VN1610** over a single transport — **Option B = COM + System Variables / WebSocket bridge** — **without a CDD**. Capabilities v1: Read DTC, Tester Present, Security Access (seed/key via the Vector DLL inside CAPL), session control, clear DTC. A **Mock ECU** runs the whole stack offline.

Components: `vector/capl/` (CAPL nodes), `bridge/` (Option B Python bridge), `mock_ecu/`, `terminal/`, `flutter_app/`, `protocol/`, `docs/`.

---

## 1a. Current sequencing priority (operator override, 2026-06-12)

- **Option A removed.** Option A (CAPL TCP server transport) was removed on 2026-06-12 due to uncertain CAPL TCP/IP API licensing on the operator's CANalyzer — see `docs/STATUS.md` §5 (R1, closed). Its CAPL code (`flexdiag_tcp.can`) and the matching Python/test code were deleted; `flexdiag_core.can` is untouched. Option B (`flexdiag_sysvar.can` + `bridge/`, M3) is now the sole transport and the active priority.
- **Flutter deferred.** `flutter_app/` (W5/M5) is paused. The Python terminal (`terminal/`) is the primary test client for all capabilities until Flutter is picked back up.

---

## 2. Roles and model assignment

Work is split into a **2-node architecture** (consolidated from the previous 5-node setup on 2026-06-12 to cut context-duplication overhead). The split preserves separation of duties between the agent that *writes* code and the agent that *reviews + ships* it. Each role is a subagent in `.claude/agents/`.

| Role | Subagent | Model | Owns |
|------|----------|-------|------|
| **Builder** | `builder` | Sonnet 4.6 | Implementation **and** testing in one TDD loop. Bridge, Mock ECU, terminal, Flutter UI, the CAPL transport node (`flexdiag_sysvar.can`), and the tests that prove them. Iterates locally until lint+tests are green, then hands the diff + test logs to `gatekeeper`. Does not commit, push, open PRs, or edit `docs/STATUS.md`. |
| **Gatekeeper** | `gatekeeper` | Opus 4.8 | Reviewer + shipper + status keeper merged. Receives diffs and test logs from `builder` (not the whole repo). Reviews against architecture/protocol/security rules, stages and commits with Conventional Commits, opens a PR against `main`, merges once CI is green, and updates `docs/STATUS.md`. Sole node allowed to touch `main`, the PR API, or `docs/STATUS.md`. |

**Why the model choices:** Builder is Sonnet because it does the bulk of daily work and benefits from speed + iteration. Gatekeeper is Opus because its review responsibility for protected areas (protocol, sysvar layout, `flexdiag_core.can`, `0x27` security path, ADRs) is the highest-stakes piece of the consolidated role; cheapening the review would defeat the gate. The trade-off — Opus also running on shipping and STATUS.md edits that were previously Sonnet/Haiku work — is the cost the 2-node architecture accepts. See §6.

> If a model alias isn't available in your Claude Code build, map it via the model-config environment variables (see Claude Code docs).

---

## 3. Workflow rules (enforced)

These restate `docs/04` for agent execution. **Violations block a merge.**

1. **Mock-first.** New behaviour is proven against the Mock ECU (software loopback) before any Vector integration.
2. **Protocol is frozen after M0.** Any change to the wire protocol (`docs/03` §1) or sysvar layout (§2) requires: a `proto=N` bump in the handshake, the spec doc, the transport, and **both** clients updated in the *same* PR, and **reviewer approval**. No partial protocol changes.
3. **Builder does not self-approve protected changes.** Separation of duties holds at the builder ↔ gatekeeper boundary. Any PR touching these paths MUST be reviewed by `gatekeeper` (acting in its reviewer capacity) before merge, with the review verdict recorded in the PR body:
   - `vector/capl/flexdiag_core.can`
   - `protocol/**` and `docs/03-TECHNICAL-DETAIL.md` (protocol/sysvar sections)
   - anything in the security (`0x27`) path
   - any ADR

   `gatekeeper` may commit, open, and merge such PRs because the *coder* (`builder`) is a different agent — but for protected changes `gatekeeper` MUST cite the specific rules it checked in the PR body as an audit trail. Protocol or sysvar changes additionally require a `proto=N` bump in the handshake, the spec doc, the transport, and BOTH clients updated in the same PR (rule §3.2).
4. **Diagnostics live in CAPL, never in COM.** The bridge only moves System Variables. Do not add diagnostic logic to the bridge.
5. **No CDD assumptions.** Only raw UDS bytes cross the protocol boundary; all DTC/DID/NRC decoding is client-side.
6. **Single transport, every capability.** A capability is "done" only when it passes on Option B. Release requires passing on CANoe *and* CANalyzer.
7. **Secrets never committed.** Real seed-key DLLs, ECU keys, and customer CAN matrices stay out of the repo. Only the *test* DLL/algorithm and Mock ECU live in-repo. Generated keys are never written to persistent logs.
8. **Every PR records its test topology** (software loopback / virtual CAN / VN1610+real ECU) and tool (CANoe/CANalyzer). `flexdiag-status` reflects this in `docs/STATUS.md`.

---

## 4. Definition of done (per change)

- Code formatted/linted (Python: `ruff`/`black`; Dart: `dart format` + `flutter analyze` clean).
- Tests added/updated and passing against the Mock ECU.
- If protocol/security/CAPL-core touched → `gatekeeper` records its review verdict (rules cited) in the PR body.
- Relevant `docs/*.md` updated in the same PR.
- `docs/STATUS.md` updated by `gatekeeper` on the same branch (separate `docs(status): …` commit).

---

## 5. Conventions (quick reference)

- Commits: Conventional Commits with scope, e.g. `feat(capl): add security key-send continuation`.
- Protocol verbs UPPERCASE; sysvars `Diag::PascalCase`; CAPL funcs `PascalCase`; Python `snake_case`; Dart `snake_case.dart`.
- Defaults: ECU qualifier `ECU1`, baud 500 kbit/s, phys req `0x7E0` / resp `0x7E8`, WS `127.0.0.1:8770`, tester-present 2000 ms suppress-positive.
- Localhost-only by default; remote binding is explicit opt-in (not part of v1 hardening).

---

## 6. Token / cost discipline

The 2-node architecture trades the previous fine-grained model split (Opus-only-for-reviews, Haiku-for-status) for fewer cross-context handoffs. The rules below are how we recover budget despite that.

1. **Default work is `builder` on Sonnet.** Implementation, testing, and the TDD loop all happen in one context — no ping-pong between a developer and tester subagent. Do not run the main/orchestrator session on Opus.
2. **`gatekeeper` runs on Opus but reads narrowly.** Gatekeeper consumes the structured handoff from `builder` (diff + test logs + a small block of metadata) — it does NOT re-explore the repo. Gatekeeper only opens source files when the handoff is missing context it genuinely needs to judge a change. Speculative greps are forbidden.
3. **Builder must hand off in the prescribed format.** If `builder` hands `gatekeeper` an unstructured dump (whole repo state, narrative summaries), `gatekeeper` REJECTS and asks for the structured block. This is the load-bearing rule for keeping Opus invocations cheap.
4. **Read narrowly, not whole docs.** Cite the exact section (e.g. "per `docs/03` §5") so subagents read with intent. Use subagents for "read a lot, return a short summary" so exploration stays out of the main context window.
5. **Keep this file lean.** `CLAUDE.md` loads every turn — details belong in `docs/`. Do not grow it with content that can be linked.
6. **One milestone per session, then close.** A session's context accumulates and every later turn costs more. Finish a milestone, let `gatekeeper` update STATUS.md, then close and reopen with `/resume`. STATUS.md is the memory — re-orienting from it is far cheaper than carrying a long history.
7. **Trim output when it's mechanical.** For status/regression, ask for a pass/fail matrix with no narrative. `gatekeeper`'s output is always the terse template in its agent definition.
8. **Measure before optimizing.** Check `/cost` after each milestone (per-model spend + cache-hit rate). Fix the most expensive thing first; don't guess. If `gatekeeper`'s Opus cost dominates without protected-area review value, that's a signal to revisit this architecture.

---

## 7. Pointers

| Need | File |
|------|------|
| Scope, phases, milestones | `docs/00-MASTER-PLAN.md` |
| Architecture, ADRs, data flow | `docs/01-SYSTEM-ARCHITECTURE.md` |
| Requirements (FR/NFR/ENV) | `docs/02-SYSTEM-REQUIREMENTS.md` |
| Protocol, sysvars, CAPL, bridge, mock, codecs | `docs/03-TECHNICAL-DETAIL.md` |
| All normative rules | `docs/04-RULES-AND-CONVENTIONS.md` |
| Vector setup + bring-up | `docs/05-CANOE-CANALYZER-SETUP.md` |
| Live project status | `docs/STATUS.md` |
| Agent role definitions | `.claude/agents/*.md` |
