---
name: team-sync
description: Fetch main, show what teammates merged since this checkout last looked, re-read docs/team/history, and summarize what affects the current user's area.
---

1. Run `git fetch origin` and `git log --no-merges --format='%h %an: %s' HEAD..origin/main`.
2. Identify the user from `git config user.email` using the table in `docs/team/INSTRUCTIONS.md`.
3. Read the `## Now` section and newest 3 log entries of every file in `docs/team/history/`
   (use `git show origin/main:docs/team/history/<name>.md` for the latest version on main).
4. Reply with at most 8 lines:
   - what teammates shipped or changed since last sync
   - any **Contract changes** that touch the user's area, and what to update
   - whether to merge main now (say so if the user's branch is behind and touches the same files)
5. Do not merge, rebase or pull unless the user says so.
