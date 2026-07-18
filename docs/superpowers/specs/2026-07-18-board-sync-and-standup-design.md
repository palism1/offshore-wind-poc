# Design: Discord board sync + morning standup delegation

**Date:** 2026-07-18
**Status:** approved (design), pending implementation plan
**Repos touched:** `discord-jobbot` (Node bridge) and `offshore-wind-poc` (standup skill + `docs/BOARD.md`)

## Goal

Bring the Discord job board (Open / In Progress / Blocked / Done, plus owner) into
the `offshore-wind-poc` repo, and give Mikko a one-command morning ritual that
scans the codebase against the board and delegates ripe jobs to subagents — with
the board updated automatically as work is claimed and finished.

## Decisions (locked in brainstorming)

1. **Morning routine = plan → approve → dispatch.** The standup presents a
   prioritized delegation plan; Mikko greenlights; then subagents are dispatched.
   No auto-dispatch without approval.
2. **Write-back = full loop.** On dispatch a job is Claimed (In Progress); on
   subagent success it is marked Done; on failure it is marked Blocked with a
   note. The Discord board stays the single source of truth.
3. **Snapshot = committed `docs/BOARD.md`.** Human-readable, written on each pull,
   committed to git for a versioned daily history.
4. **Code home.** All Discord API code lives in `discord-jobbot` (it already owns
   the bot token + guild/forum IDs). The standup skill lives in
   `offshore-wind-poc/.claude/` and shells out to the bridge script.

## Components

### 1. `discord-jobbot/scripts/board.mjs` — the bridge

A standalone Node script (ESM, no new deps; same `.dev.vars` loading pattern as
`scripts/register.js`). Reads `DISCORD_TOKEN`, `DISCORD_GUILD_ID`,
`FORUM_CHANNEL_ID` from `.dev.vars` or the environment.

Reuses the status-tag conventions already in `src/server.js`:
`STATUS_TAGS = ['Open','In Progress','Blocked','Done']`, and the owner is parsed
from JoBot's control message via the same `Owner: <@id>` shape the bot writes.

**Subcommand `pull`** (read-only):
- Lists active threads via `GET /guilds/{guildId}/threads/active` and archived
  ones via `GET /channels/{forumId}/threads/archived/public` (so Done posts are
  included), filtered to `parent_id === FORUM_CHANNEL_ID`.
- For each thread resolves: title, thread URL, **status tag**, **category tags**
  (everything that isn't a status tag), and **owner** (parse the control message;
  resolve owner id → display name via `GET /guilds/{guildId}/members/{id}`,
  falling back to the `<@id>` mention if the lookup fails).
- Writes `../offshore-wind-poc/docs/BOARD.md` (path overridable with `--out`),
  grouped by status: In Progress, Open, Blocked, Done, with a `synced <ISO
  timestamp>` header line.
- Also prints the same records as JSON to **stdout**, so the standup skill gets
  structured data without a second committed file.

**Subcommand `set <threadId> <claim|done|block> [--dry-run]`** (write):
- Performs the same tag swap the JoBot buttons do (keep non-status tags, drop
  status tags, add the target; `done` also archives + locks the thread).
- `--dry-run` prints the intended `applied_tags` change and does not call Discord.

**Exit codes:** non-zero on missing config, HTTP failure, or unknown subcommand,
with a one-line human-readable reason on stderr.

### 2. `offshore-wind-poc/.claude/skills/standup/SKILL.md` — the ritual

Invoked by `/standup` (or "run the standup"). Steps the assistant follows:

1. Run `node ../discord-jobbot/scripts/board.mjs pull` (path relative to the
   offshore-wind-poc repo root) → refreshes `docs/BOARD.md` and returns live JSON.
2. Scan the repo to judge readiness: `git log`, open branches, `docs/PLAN.md`,
   `docs/HANDOFF.md`, and TODO markers.
3. Cross-reference board ↔ repo and present a **prioritized delegation plan** in
   three buckets:
   - **Ripe to dispatch** — Open/unclaimed jobs whose spec exists and whose
     blockers are cleared; each annotated with the suggested subagent and the
     spec/section it should follow.
   - **Human-only** — jobs that need Mikko (e.g. obtaining the EIA API key).
   - **Blocked / skip** — with the reason and what unblocks them.
4. On Mikko's approval, for each greenlit job: `board.mjs set <id> claim` →
   dispatch a subagent → on success `board.mjs set <id> done`, on failure
   `board.mjs set <id> block` (and post a short note). Then commit `docs/BOARD.md`.

The skill never dispatches or writes to Discord before Mikko approves the plan.

## Data flow

```
Discord forum  ⇄  board.mjs (bot token)  →  docs/BOARD.md (committed) + JSON (stdout)
                                              ↓
                          /standup skill (assistant, in offshore-wind-poc)
                                              ↓
                    delegation plan → Mikko approves → dispatch subagents
                                              ↓
                    board.mjs set claim/done/block  →  Discord updated  →  commit BOARD.md
```

## Error handling & safety

- Missing JoBot control message on a thread → owner reported as *unassigned*.
- Missing token/guild/forum config → `board.mjs` exits non-zero with a clear message.
- Discord rate-limit (HTTP 429) → honor `retry_after` and back off.
- `set` is only invoked after Mikko approves; a failed subagent marks the job
  **Blocked**, never Done.
- `pull` is strictly read-only, so the daily sync cannot damage the board.

## Testing

- `pull`: run it and eyeball `docs/BOARD.md` against the live Discord forum.
- `set`: exercise `--dry-run` first, then verify against a throwaway forum post
  before trusting it on real jobs.
- Owner parsing and status/category tag classification are pure functions on the
  thread + control-message payload — unit-test them with captured sample payloads
  (no network).

## Out of scope (YAGNI)

- No always-on service; the pull runs on demand from the standup.
- No pushing repo-side tasks back into Discord as new posts (board is authored in
  Discord).
- No priority/urgency modeling beyond what the board already carries.
</content>
