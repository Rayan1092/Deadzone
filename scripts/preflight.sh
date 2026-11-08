#!/bin/sh
# Shared checks and exit code match preflight.ps1. Activation stays in this process.
case $0 in
    */*) preflight_dir=${0%/*} ;;
    *) preflight_dir=. ;;
esac
case $preflight_dir in -*) preflight_dir=./$preflight_dir ;; esac
preflight_root=$(CDPATH= cd "$preflight_dir/.." 2>/dev/null && pwd) || {
    printf '%s\n' 'FAIL preflight: repository directory unavailable'
    exit 1
}
preflight_activation=failed
if [ -f "$preflight_root/.venv/bin/activate" ]; then
    . "$preflight_root/.venv/bin/activate" >/dev/null 2>&1 && preflight_activation=ok
elif [ -f "$preflight_root/.venv/Scripts/activate" ]; then
    . "$preflight_root/.venv/Scripts/activate" >/dev/null 2>&1 && preflight_activation=ok
fi
if [ -x "$preflight_root/.venv/bin/python" ]; then
    preflight_python="$preflight_root/.venv/bin/python"
elif [ -x "$preflight_root/.venv/Scripts/python.exe" ]; then
    preflight_python="$preflight_root/.venv/Scripts/python.exe"
    if [ "$preflight_activation" = ok ] && command -v cygpath >/dev/null 2>&1; then
        VIRTUAL_ENV=$(cygpath -w "$VIRTUAL_ENV")
        export VIRTUAL_ENV
    fi
else
    preflight_python=$(command -v py || command -v python3 || command -v python) || {
        printf '%s\n' 'FAIL .venv activation: Python unavailable'
        exit 1
    }
fi
exec "$preflight_python" "$preflight_root/scripts/preflight.py" --activation "$preflight_activation"
