#!/usr/bin/env python3
"""SessionStart + UserPromptSubmit hook: keep Claude's team context current.

On session start it points Claude at docs/team/. Before each prompt it checks
whether HEAD (or origin/main) moved since this checkout last looked: a pull,
merge, rebase or branch switch. When teammates' commits arrived it injects the
commit list and the history-file diffs so Claude re-reads them before answering.
State lives in .git (per worktree), never in the repo.
"""
import json
import os
import subprocess
import sys

HISTORY = "docs/team/history"
MAX_DIFF_LINES = 160


def git(*args):
    r = subprocess.run(["git", *args], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else ""


def load_state(path):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return {}


def save_state(path, state):
    try:
        with open(path, "w") as f:
            json.dump(state, f)
    except Exception:
        pass


def teammate_commits(old, new, me):
    """Non-merge commits in old..new not authored by me."""
    if not old or not new or old == new:
        return []
    if not git("cat-file", "-t", old):  # old commit gone (gc, force push)
        rng = [new, "-n", "15"]
    else:
        rng = [f"{old}..{new}"]
    out = git("log", "--no-merges", "--format=%h%x09%ae%x09%an%x09%s", *rng)
    rows = []
    for line in out.splitlines():
        parts = line.split("\t", 3)
        if len(parts) == 4 and parts[1].lower() != me:
            rows.append(parts)
    return rows


def history_diff(old, new):
    if not old or not git("cat-file", "-t", old):
        return ""
    d = git("diff", "--unified=0", old, new, "--", HISTORY)
    lines = [l for l in d.splitlines() if l.startswith("+") and not l.startswith("+++")]
    if len(lines) > MAX_DIFF_LINES:
        lines = lines[:MAX_DIFF_LINES] + [f"... ({len(lines) - MAX_DIFF_LINES} more lines, read the files)"]
    return "\n".join(lines)


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        payload = {}
    event = payload.get("hook_event_name", "UserPromptSubmit")

    root = payload.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR")
    if root:
        os.chdir(root)
    git_dir = git("rev-parse", "--absolute-git-dir")
    if not git_dir:
        return
    state_path = os.path.join(git_dir, "deadzone-team-sync.json")
    state = load_state(state_path)
    me = git("config", "user.email").lower()

    head = git("rev-parse", "HEAD")
    remote = git("rev-parse", "--verify", "--quiet", "origin/main")
    msgs, notes = [], []

    # 1) HEAD moved: commits now in the working tree.
    landed = teammate_commits(state.get("head"), head, me)
    if landed:
        lines = "\n".join(f"- {h} {n}: {s}" for h, _, n, s in landed[:25])
        hist = history_diff(state.get("head"), head)
        msgs.append(
            "TEAM SYNC: new teammate commits are now in this checkout "
            f"({len(landed)} since this session last looked):\n{lines}"
            + (f"\n\nNew lines in {HISTORY}/:\n{hist}" if hist else "")
            + "\n\nBefore answering the user: re-read the `## Now` section and new log entries of "
            f"each changed file in {HISTORY}/, check any **Contract changes** against the user's area, "
            "and tell the user in 2 to 4 lines what affects them (see docs/team/INSTRUCTIONS.md Rule 1)."
        )
        notes.append(f"team sync: {len(landed)} new teammate commit(s), Claude is re-reading history")

    # 2) origin/main moved (someone fetched) but it isn't merged here yet.
    if remote and remote != state.get("remote"):
        unmerged = teammate_commits(head, remote, me)
        if unmerged and state.get("remote"):
            lines = "\n".join(f"- {h} {n}: {s}" for h, _, n, s in unmerged[:15])
            msgs.append(
                "TEAM SYNC: origin/main has teammate commits that are NOT merged into this branch yet:\n"
                f"{lines}\nMention this to the user if their task touches the same area, and "
                f"read them with `git show origin/main:{HISTORY}/<name>.md`."
            )

    if event == "SessionStart":
        msgs.insert(
            0,
            "TEAM CONTEXT: this repo is worked on from 3 laptops with separate Claude sessions. "
            "Follow docs/team/INSTRUCTIONS.md. Before starting work, read the `## Now` section and "
            f"newest 3 log entries of every file in {HISTORY}/. Before any commit, add an entry to "
            "your own history file and stage it (a hook enforces this).",
        )

    save_state(state_path, {"head": head, "remote": remote or state.get("remote")})

    if msgs:
        out = {"hookSpecificOutput": {"hookEventName": event, "additionalContext": "\n\n".join(msgs)}}
        if notes:
            out["systemMessage"] = "; ".join(notes)
        print(json.dumps(out))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass  # never block a prompt because of this hook
