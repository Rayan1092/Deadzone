#!/usr/bin/env python3
"""PreToolUse(Bash) hook: a commit made through Claude must carry a history entry.

Blocks `git commit` unless a file under docs/team/history/ is part of it.
Skipped for --amend, merge commits, and messages containing [no-history].
"""
import json
import os
import re
import subprocess
import sys

HISTORY = "docs/team/history/"


def git(*args):
    r = subprocess.run(["git", *args], capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else ""


def main():
    payload = json.load(sys.stdin)
    cmd = (payload.get("tool_input") or {}).get("command", "")
    if not re.search(r"\bgit\s+(-C\s+\S+\s+)?commit\b", cmd):
        return
    if "--amend" in cmd or "[no-history]" in cmd:
        return
    # Run git where the commit runs: `git -C dir`, a leading `cd dir &&`, else the session cwd.
    m = re.search(r"\bgit\s+-C\s+(\"[^\"]+\"|'[^']+'|\S+)\s+commit\b", cmd) or \
        re.match(r"\s*cd\s+(\"[^\"]+\"|'[^']+'|\S+)\s*&&", cmd)
    base = payload.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or "."
    os.chdir(base)
    if m:
        os.chdir(os.path.expanduser(m.group(1).strip("\"'")))
    git_dir = git("rev-parse", "--absolute-git-dir").strip()
    if not git_dir or os.path.exists(os.path.join(git_dir, "MERGE_HEAD")):
        return

    staged = set(git("diff", "--cached", "--name-only").split())
    # `git add ... && git commit` or `commit -a`: files get staged by the same command.
    if re.search(r"\bgit\s+add\b|\bcommit\b[^&;|]*\s(-[a-zA-Z]*a[a-zA-Z]*|--all)\b", cmd):
        for line in git("status", "--porcelain", "--untracked-files=all").splitlines():
            path = line[3:].split(" -> ")[-1].strip('"')
            staged.add(path)
    if not staged:
        return  # nothing to commit, let git say so
    if any(p.startswith(HISTORY) for p in staged):
        return

    me = git("config", "user.email").strip()
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": (
                "Team protocol: this commit has no history entry. Before committing, add an entry at the top "
                f"of `## Log` in your own {HISTORY}<name>.md (match git email {me} in docs/team/INSTRUCTIONS.md), "
                "update its `## Now` section, stage it, then retry the commit. For trivial commits put "
                "[no-history] in the message."
            ),
        }
    }))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass  # a broken guard must never block work
