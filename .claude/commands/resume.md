---
description: Re-orient on the FlexDiag project from disk and report the next action.
---

You are the orchestrator for FlexDiag. Re-orient from disk, not from remembered context.

1. Read `CLAUDE.md` (operating contract, 2-node roles, rules) and `docs/STATUS.md` (live state).
2. Skim `docs/RUNBOOK.md` so you know the per-milestone prompts and human-gates.
3. Report back, concisely:
   - **Current milestone** (M0, M1, M3, M5, M6 — M2/M4 removed along with Option A) and whether it's Not started / In progress / Done.
   - **Capability matrix** snapshot: what's ✅ / 🟡 / ⬜ across Option B, CANoe, CANalyzer, Mock ECU.
   - **Open blockers** from STATUS.md §5 (especially any unresolved human-gate, e.g. seed-key DLL, real-hardware run).
   - **The single next action** — the one concrete step that moves us forward, framed as a `builder` task.

## Routing (2-node architecture)

All work flows: **operator → `builder` → `gatekeeper` → `main`**. There are no other paths.

- **`builder`** (Sonnet) owns implementation + tests in a single TDD loop. Invoke it with a clear requirement (cite the FR or `docs/03` §-ref). It iterates locally until lint+tests are green, then emits the structured handoff block defined in `.claude/agents/builder.md`.
- **`gatekeeper`** (Opus) owns review + commit + PR + merge + STATUS.md. Invoke it ONLY with the handoff block from `builder` — never with "here, look at the repo". Gatekeeper either rejects (back to `builder`) or ships (PR opened, merged, STATUS.md updated). Gatekeeper is the only node permitted to touch `main`, the GitHub PR API, or `docs/STATUS.md`.
- **Do not** invoke `gatekeeper` to write code, do not invoke `builder` to open PRs, and do not touch `main` from this orchestrator session.

For protected-area work (protocol, sysvar layout, `flexdiag_core.can`, `0x27` security path, ADRs), the flow is the same — but `gatekeeper` must cite the specific rules it checked in the PR body (CLAUDE.md §3 rule 3).

4. Then **STOP and wait for my go**. Do not start work, do not advance a milestone, do not invoke `builder` or `gatekeeper`, and do not touch protected areas without my explicit instruction.

If `docs/STATUS.md` shows everything ⬜ (fresh project), say so and recommend running the kickoff prompt in `docs/RUNBOOK.md` §1 to start at M0.
