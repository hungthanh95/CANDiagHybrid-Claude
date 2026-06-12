# CLAUDE.md — FlexDiag

This file is the **operating contract** for AI agents working on FlexDiag. Claude Code loads it automatically. It defines who does what, which model plays which role, and the rules that must never be violated. Detailed specs live in `docs/`.

> **Read before acting:** `docs/00-MASTER-PLAN.md` (scope/phases), `docs/03-TECHNICAL-DETAIL.md` (the protocol contract), `docs/04-RULES-AND-CONVENTIONS.md` (normative rules). The protocol and sysvar layout are **frozen at milestone M0** — see below.

---

## 1. What this project is

A UDS (ISO 14229) diagnostic tool. A **Flutter** operator UI and a **Python terminal** test client drive **Vector CANoe/CANalyzer + VN1610** over two interchangeable transports (**A = CAPL TCP server**, **B = COM + System Variables / WebSocket bridge**), **without a CDD**. Capabilities v1: Read DTC, Tester Present, Security Access (seed/key via the Vector DLL inside CAPL), session control, clear DTC. A **Mock ECU** runs the whole stack offline.

Components: `vector/capl/` (CAPL nodes), `bridge/` (Option B Python bridge), `mock_ecu/`, `terminal/`, `flutter_app/`, `protocol/`, `docs/`.

---

## 1a. Current sequencing priority (operator override, 2026-06-12)

- **Option B first.** Option A (CAPL TCP) Vector bring-up depends on an uncertain CAPL TCP/IP API license. The Option A CAPL code (`flexdiag_core.can`, `flexdiag_tcp.can`) is written and `flexdiag-reviewer`-approved (M2) but its Vector-side verification is parked. Prioritize **Option B** (`flexdiag_sysvar.can` + `bridge/`, M3) next — both transports still ship eventually, this only reorders the work.
- **Flutter deferred.** `flutter_app/` (W5/M5) is paused. The Python terminal (`terminal/`) is the primary test client for all capabilities until Flutter is picked back up.

---

## 2. Roles and model assignment

Work is split so the strongest model handles low-volume / high-stakes decisions and cheaper models handle high-volume repetitive work. Each role is implemented as a subagent in `.claude/agents/`.

| Role | Subagent | Model | Owns |
|------|----------|-------|------|
| **Architect / Reviewer** | `flexdiag-reviewer` | Opus 4.8 | Reviews every change to the wire protocol, sysvar layout, `flexdiag_core.can`, security (`0x27`) flow, and ADRs. Approves or blocks merges into protected areas. |
| **Developer** | `flexdiag-developer` | Sonnet 4.6 | Implements bridge, Mock ECU, terminal, Flutter UI, and CAPL transport nodes against the frozen protocol. |
| **Tester** | `flexdiag-tester` | Sonnet 4.6 (writes tests) / Haiku 4.5 (runs regressions) | Writes unit tests (codecs), negative-path tests (NRC `0x78`/`0x35`/`0x33`), and runs `.flex` regression scripts against the Mock ECU. |
| **Status / PM** | `flexdiag-status` | Haiku 4.5 | Keeps `docs/STATUS.md` current: milestone state (M0–M6), capability × transport × tool pass matrix, and FR→test traceability. |
| **PR shipper** | `flexdiag-shipper` | Sonnet 4.6 | Owns the PR lifecycle: opens PRs from feature branches to `main`, reviews them against `docs/04` §7 (git rules), and merges once CI is green and approvals are in. Routes protected-area PRs to `flexdiag-reviewer` for approval; does **not** self-approve them. |

> If a model alias isn't available in your Claude Code build, map it via the model-config environment variables (see Claude Code docs). For larger architectural decisions you may run the reviewer on a higher tier (e.g. Fable 5) — but everyday reviews use Opus.

---

## 3. Workflow rules (enforced)

These restate `docs/04` for agent execution. **Violations block a merge.**

1. **Mock-first.** New behaviour is proven against the Mock ECU (software loopback) before any Vector integration.
2. **Protocol is frozen after M0.** Any change to the wire protocol (`docs/03` §1) or sysvar layout (§2) requires: a `proto=N` bump in the handshake, the spec doc, **both** transports, and **both** clients updated in the *same* PR, and **reviewer approval**. No partial protocol changes.
3. **Developer does not self-approve protected changes.** Any PR touching these paths MUST be reviewed by `flexdiag-reviewer` before merge:
   - `vector/capl/flexdiag_core.can`
   - `protocol/**` and `docs/03-TECHNICAL-DETAIL.md` (protocol/sysvar sections)
   - anything in the security (`0x27`) path
4. **Diagnostics live in CAPL, never in COM.** The bridge only moves System Variables. Do not add diagnostic logic to the bridge.
5. **No CDD assumptions.** Only raw UDS bytes cross the protocol boundary; all DTC/DID/NRC decoding is client-side.
6. **Both transports, every capability.** A capability is "done" only when it passes on Option A *and* Option B. Release requires passing on CANoe *and* CANalyzer.
7. **Secrets never committed.** Real seed-key DLLs, ECU keys, and customer CAN matrices stay out of the repo. Only the *test* DLL/algorithm and Mock ECU live in-repo. Generated keys are never written to persistent logs.
8. **Every PR records its test topology** (software loopback / virtual CAN / VN1610+real ECU) and tool (CANoe/CANalyzer). `flexdiag-status` reflects this in `docs/STATUS.md`.

---

## 4. Definition of done (per change)

- Code formatted/linted (Python: `ruff`/`black`; Dart: `dart format` + `flutter analyze` clean).
- Tests added/updated and passing against the Mock ECU.
- If protocol/security/CAPL-core touched → reviewed by `flexdiag-reviewer`.
- Relevant `docs/*.md` updated in the same PR.
- `docs/STATUS.md` updated by `flexdiag-status`.

---

## 5. Conventions (quick reference)

- Commits: Conventional Commits with scope, e.g. `feat(capl): add security key-send continuation`.
- Protocol verbs UPPERCASE; sysvars `Diag::PascalCase`; CAPL funcs `PascalCase`; Python `snake_case`; Dart `snake_case.dart`.
- Defaults: ECU qualifier `ECU1`, baud 500 kbit/s, phys req `0x7E0` / resp `0x7E8`, TCP `9000`, WS `127.0.0.1:8770`, tester-present 2000 ms suppress-positive.
- Localhost-only by default; remote binding is explicit opt-in (not part of v1 hardening).

---

## 6. Token / cost discipline

Spend the strongest models only where a mistake is expensive. These are enforced, not suggestions.

1. **Opus is for protected areas only.** `flexdiag-reviewer` (Opus) runs on changes touching the protocol, sysvar layout, `flexdiag_core.can`, the `0x27` security path, or ADRs — nothing else. Routine component work, Flutter UI, and ordinary refactors do NOT call Opus.
2. **Push mechanical work to Haiku.** Status updates, STATUS.md edits, diff/summary tasks, and re-running existing regression scripts go to `flexdiag-status` / a Haiku run, never to Opus or Sonnet.
3. **Default work is Sonnet.** Implementation and orchestration use Sonnet. Do not run the main/orchestrator session on Opus.
4. **Read narrowly, not whole docs.** Cite the exact section (e.g. "per `docs/03` §5") so agents read with intent. Use subagents for "read a lot, return a short summary" so exploration stays out of the main context window.
5. **Keep this file lean.** `CLAUDE.md` loads every turn — details belong in `docs/`. Do not grow it with content that can be linked.
6. **One milestone per session, then close.** A session's context accumulates and every later turn costs more. Finish a milestone, let `flexdiag-status` update STATUS.md, then close and reopen with `/resume`. STATUS.md is the memory — re-orienting from it is far cheaper than carrying a long history.
7. **Trim output when it's mechanical.** For status/regression, ask for a pass/fail matrix with no narrative.
8. **Measure before optimizing.** Check `/cost` after each milestone (per-model spend + cache-hit rate). Fix the most expensive thing first; don't guess.

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
