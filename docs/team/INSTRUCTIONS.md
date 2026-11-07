# Team context protocol (for every Claude session on every laptop)

Three people, three laptops, three separate Claude sessions, plus one test laptop.
No session can see another session's chat. **The repo is the only shared memory.**
These files carry what each person's Claude learned, so nobody has to copy-paste
context between laptops again.

```
docs/team/
  INSTRUCTIONS.md      this file (the protocol)
  history/rayan.md     Rayan, robots + ML      (only Rayan's sessions write here)
  history/aziz.md      Aziz, backend + network (only Aziz's sessions write here)
  history/yusuf.md     Yusuf, web frontend     (only Yusuf's sessions write here)
```

Each person writes **only their own file**, so merges never conflict.

## Who am I?

Match `git config user.email` to a file:

| git email | file | owns |
|---|---|---|
| yanodiya@gmail.com | `history/rayan.md` | `server/deadzone/robot/`, `ml/`, `data/floorplans/` |
| a.captain.b@gmail.com, 171593652+acaptainb@users.noreply.github.com | `history/aziz.md` | `sim.py`, `app.py`, `floorplan.py`, `network/`, `command/` |
| yusnus2007@gmail.com | `history/yusuf.md` | `web/` |

If your email isn't listed, ask the user which person they are and add the email here.

## Rule 1: read before you work

At session start, and whenever the hook says new commits arrived:

1. Read the `## Now` section of **all three** history files, plus the newest 3 log entries in each.
2. If a teammate's entry says **Contract changes**, read that part of `docs/PLAN.md`, `docs/DTN.md`
   or `docs/PHONE-PLANNING.md` before you touch code that sends or receives those messages.
3. Tell the user in 2 to 4 lines what changed that affects their area. Skip anything that doesn't.

The `team_sync` hook does the detection. It runs on session start and before every prompt. When `HEAD` has moved
(pull, merge, rebase, branch switch) and the new commits include teammates' commits, it puts
the commit list and history-file diffs into your context. **Act on it before answering the prompt.**

## Rule 2: write before you commit

Every commit made through Claude must also stage the author's own history file.
The `history_guard` hook blocks `git commit` when no file under `docs/team/history/` is part of it.

Before committing:

1. Look at what is being committed (`git diff --cached`, or the working tree if it will be added).
2. Add a log entry at the **top** of `## Log` in your own file (newest first) using the template below.
3. Rewrite your `## Now` section so it is true after this commit.
4. Stage the history file with the code. One commit carries both.

Keep entries short: facts a teammate's Claude needs, not a diary. Leave out code that git already shows.

Escape hatches: amend commits and merge commits are not checked. Putting `[no-history]` in the commit
message skips the check. Use it only for trivial commits (typos, formatting).

If someone commits **by hand** in a terminal, the guard can't see it. Next time they talk to
Claude, run `/log-work` and it writes entries for commits that aren't in the history yet.

### Log entry template

```markdown
### 2026-11-07 18:40 · branch-name · short title
- **Did:** what now works, in user-visible terms. Mention files only when it helps.
- **Contract changes:** message shapes, endpoints, event names, keys, floorplan coords. "none" if none.
- **Heads-up for others:** what a teammate must do or avoid because of this. "none" if none.
- **Next:** what this person does next.
```

### `## Now` section (always kept current, overwrite it)

- **Working on:** branch and task
- **Works on main:** short list
- **In flight (not merged):** branch and what it adds
- **Blocked on / need from others:** who and what
- **Promises to others:** shapes or features teammates are building against

## Rule 3: contracts are the danger zone

Anything another laptop builds against goes in **Contract changes**: WebSocket messages, REST
routes, event names, telemetry fields, keyboard shortcuts, floorplan coordinates. Never change a
contract without writing it there and in the PR description (CLAUDE.md already requires the PR part).

## The test laptop

It runs only `main`: `git pull` then restart the servers. It doesn't write a history file. If
its Claude finds a bug, tell the user which person owns it (see the table above) and the
exact repro. Don't fix code there.

## Slash commands in this repo

- `/team-sync`: fetch, show what teammates merged since you last looked, re-read the history, summarize what affects you.
- `/log-work`: write history entries for your commits that don't have one yet (for hand-made commits).
