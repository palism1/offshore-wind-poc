---
name: standup
description: Use when Mikko says "run the standup", "morning standup", or "scan the board and delegate" — pulls the live Discord job board, cross-references it against repo readiness, and presents a prioritized delegation plan for approval before dispatching any subagents.
---

# Standup

## Overview

The morning ritual for this repo: refresh the Discord job board, judge which
open jobs are actually ready to hand to a subagent, and present a delegation
plan. Nothing is dispatched and nothing is written back to Discord until Mikko
explicitly approves the plan.

Board state lives in Discord; `discord-jobbot/scripts/board.mjs` is the only
code that talks to Discord (bot token + guild/forum IDs live in that repo's
`.dev.vars`). This skill only shells out to it — it does not call the Discord
API directly.

## Ritual

### 1. Pull the board

From the `offshore-wind-poc` repo root, run:

```
node ../discord-jobbot/scripts/board.mjs pull
```

This is read-only. It refreshes `docs/BOARD.md` in this repo (grouped by
status: In Progress, Open, Blocked, Done, with a `synced <ISO timestamp>`
header) and prints the same records as JSON to stdout — use the JSON for the
cross-reference in step 3, not just the rendered markdown.

If the command fails (missing config, network, HTTP error), stop and report
the exact stderr line to Mikko — do not guess at board state.

### 2. Scan repo readiness

Independently of the board, check what state the repo is actually in:

- `git log` (recent commits, what's landed since the last standup)
- Open branches (`git branch -a`) — is there already in-flight work for a
  board job?
- `docs/PLAN.md` — which phases are DONE / NOT STARTED / BLOCKED
- `docs/HANDOFF.md` — anything flagged as needing attention or a decision
- TODO markers in source (`grep -rn "TODO\|FIXME"` or similar) that map to
  board jobs

### 3. Present a prioritized delegation plan

Cross-reference the board JSON against repo readiness and present three
buckets. Do not skip a bucket even if it's empty — say so explicitly.

- **Ripe to dispatch** — jobs tagged Open (unclaimed) whose spec already
  exists in the repo and whose blockers are clear. For each: the job title,
  Discord thread URL, suggested subagent type, and the spec/doc section it
  should follow.
- **Human-only** — jobs that need Mikko directly (credentials, an account,
  a judgment call only he can make, e.g. obtaining an API key). State why.
- **Blocked / skip** — jobs already tagged Blocked, or Open jobs with no
  spec/unclear scope yet. State the reason and what would unblock them.

Also flag anything already **In Progress** on the board that has no
corresponding recent commit or branch — it may be stale and worth a nudge,
but do not touch its board state without approval.

**Stop here.** This skill never dispatches a subagent or calls
`board.mjs set` before Mikko reviews this plan and explicitly approves it
(in full or a subset). Do not treat silence or an unrelated reply as
approval.

### 4. On approval, execute per greenlit job

For each job Mikko greenlit, in order:

1. Claim it on the board:
   ```
   node ../discord-jobbot/scripts/board.mjs set <threadId> claim
   ```
2. Dispatch the suggested subagent for that job, per the plan from step 3.
3. On subagent success:
   ```
   node ../discord-jobbot/scripts/board.mjs set <threadId> done
   ```
4. On subagent failure:
   ```
   node ../discord-jobbot/scripts/board.mjs set <threadId> block
   ```
   and add a short note to Mikko (in chat, not Discord) describing what
   failed and why it's blocked rather than done.

After all greenlit jobs are processed, run `pull` again (step 1) so
`docs/BOARD.md` reflects the final state, then commit `docs/BOARD.md` in this
repo with a message summarizing what moved.

### Safety

- `pull` is read-only and safe to run any time, including outside this
  ritual.
- `set` (claim/done/block) is a write to live Discord state. It is only ever
  invoked in step 4, after Mikko has approved the specific job in step 3.
- Never mark a job Done on a failed or partially-completed subagent run —
  mark it Blocked with a note instead.
- This skill does not create git branches, push to any remote, or modify
  Discord outside of `board.mjs set` calls explicitly tied to an approved
  job.
