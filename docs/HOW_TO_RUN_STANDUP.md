# How to run the morning standup (plain-English guide)

This guide assumes you know nothing about coding. Just follow it top to bottom.
Everything here happens on the Mac where the project lives.

There are **two things** you can do:

- **A. Just refresh the board** — pulls the latest from Discord into a file you can
  read. Takes 10 seconds. No AI, nothing changes on Discord.
- **B. The full morning standup** — the assistant reads the board, looks at the
  code, and hands you a to-do plan you approve. This is the main event.

You can always do A on its own. B does A for you automatically, so most mornings
you'll just do B.

---

## First: how to open the "Terminal"

The Terminal is a plain typing window. To open it:

1. Hold **Command (⌘)** and press the **Spacebar**. A little search box appears.
2. Type **Terminal** and press **Return (Enter)**.
3. A window opens where you can type commands. That's it — leave it open.

You "run" a command by typing it (or pasting it) and pressing **Return**. To paste,
use **Command (⌘) + V**.

---

## A. Just refresh the board (10 seconds)

1. Open the Terminal (see above).
2. Copy this line, paste it into the Terminal, and press **Return**:

   ```
   cd ~/Desktop/discord-jobbot && node scripts/board.mjs pull
   ```

3. Wait a few seconds. When it's done it prints a bunch of text and stops. That's
   normal — it just means it finished.
4. To read the result, open this file in your editor (or double-click it in
   Finder):

   ```
   ~/Desktop/offshore-wind-poc/docs/BOARD.md
   ```

That file now shows every job on the Discord board, sorted into **In Progress**,
**Open**, **Blocked**, and **Done**, with who owns each one. It's a snapshot of
Discord at the moment you ran it. Nothing on Discord was changed.

> **"Owner: _unassigned_" on most jobs is normal.** A job only gets an owner once
> someone clicks the green **Claim** button on that post in Discord. Names in the
> job *titles* (— Alexander, — Mitchell) are just labels, not owners.

---

## B. The full morning standup (the main routine)

This is what you'll usually run. The assistant refreshes the board, looks at the
project's code to see what's actually ready to work on, and gives you a plan.

1. Open the Terminal.
2. Copy, paste, press **Return** — this moves into the project folder:

   ```
   cd ~/Desktop/offshore-wind-poc
   ```

3. Copy, paste, press **Return** — this starts the assistant:

   ```
   claude
   ```

   (You'll see a welcome screen and a prompt to type into.)

4. Type this and press **Return**:

   ```
   /standup
   ```

5. Wait. The assistant will:
   - refresh the board (same as option A),
   - read the project to judge what's ready,
   - then show you a **plan** split into three groups:
     - **Ripe to dispatch** — jobs that are ready to be worked on now.
     - **Needs you** — jobs only a human can do (for example, signing up for an
       API key).
     - **Blocked / skip** — jobs waiting on something else, with the reason.

6. **Read the plan.** Nothing has happened yet — it's only a proposal.

7. Tell the assistant what to do, in plain English. For example:
   - "Go ahead with all the ripe ones." — it starts working on them.
   - "Just do the first one." — it does only that.
   - "None for now, thanks." — it stops and does nothing.

8. For each job you approve, the assistant does the work **and updates Discord for
   you**: the post gets marked **In Progress** while it's working, then **Done**
   when it succeeds (or **Blocked**, with a note, if it hits a problem). You don't
   touch Discord yourself.

9. When you're finished, you can close the Terminal window. To leave the assistant
   first, type `/exit` and press **Return** (optional — closing the window is fine
   too).

---

## If something doesn't look right

- **"command not found: claude"** — the assistant isn't installed on this Mac, or
  you're in a different account. Ask whoever set it up.
- **"command not found: node"** — same idea; the project's tools aren't installed
  on this Mac.
- **The board looks empty or errors mention "token" / "config"** — the Discord
  connection settings aren't in place. The file `~/Desktop/discord-jobbot/.dev.vars`
  holds them; if it's missing, the bot setup needs finishing.
- **A job you expected isn't there** — only posts in the job-board **forum
  channel** show up. Posts in other channels are ignored on purpose.

You can rerun either option as many times as you like — refreshing the board never
harms anything, and the standup never changes Discord until you say yes.

---

## The one-sentence version

**Most mornings:** open Terminal → paste `cd ~/Desktop/offshore-wind-poc` → paste
`claude` → type `/standup` → read the plan → say which jobs to do.
