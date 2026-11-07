---
name: log-work
description: Write docs/team/history entries for the user's recent commits that have no entry yet (e.g. commits made by hand outside Claude), then commit the history file.
---

1. Identify the user's history file from `git config user.email` using the table in `docs/team/INSTRUCTIONS.md`.
2. List the user's recent commits: `git log --author="$(git config user.email)" --no-merges -n 15 --format='%h %ad %s' --date=format:'%Y-%m-%d %H:%M'`.
3. Read the user's history file and work out which commits are not covered by an entry yet (match by title, branch and date).
4. For each uncovered commit (or group of related commits), read `git show --stat <hash>` and the key parts of the diff, then add an entry at the top of `## Log` using the template in `docs/team/INSTRUCTIONS.md`. Flag every message shape, endpoint, event, key or coordinate change under **Contract changes**.
5. Rewrite `## Now` so it is accurate.
6. Show the user the new entries, then commit only the history file with the message `History: log recent work`.
