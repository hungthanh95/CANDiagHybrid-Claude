---
description: Re-orient on the FlexDiag project from disk and report the next action.
---

You are the orchestrator for FlexDiag. Re-orient from disk, not from remembered context.

1. Read `CLAUDE.md` (operating contract, roles, rules) and `docs/STATUS.md` (live state).
2. Skim `docs/RUNBOOK.md` so you know the per-milestone prompts and human-gates.
3. Report back, concisely:
   - **Current milestone** (M0–M6) and whether it's Not started / In progress / Done.
   - **Capability matrix** snapshot: what's ✅ / 🟡 / ⬜ across Option A, Option B, CANoe, CANalyzer, Mock ECU.
   - **Open blockers** from STATUS.md §5 (especially any unresolved human-gate, e.g. CAPL TCP API check, seed-key DLL, real-hardware run).
   - **The single next action** — the one concrete step that moves us forward, and which subagent would do it.
4. Then **STOP and wait for my go**. Do not start work, do not advance a milestone, and do not touch protected areas (protocol, sysvar layout, `flexdiag_core.can`, security path) or any human-gate step without my explicit instruction.

If `docs/STATUS.md` shows everything ⬜ (fresh project), say so and recommend running the kickoff prompt in `docs/RUNBOOK.md` §1 to start at M0.
