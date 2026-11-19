#!/usr/bin/env bash
# Stop hook: speak the 🔊 part of the finished reply, unless speak-now.sh already spoke that exact text.
set -u
HOOK="$(cat)"
eval "$(printf '%s' "$HOOK" | python3 -c '
import json, shlex, sys
try: d = json.load(sys.stdin)
except Exception: d = {}
print("export CONVERSE_SOURCE=" + shlex.quote(str(d.get("session_id") or "")))
print("export CONVERSE_CWD=" + shlex.quote(str(d.get("cwd") or "")))')"
SELF="$(python3 -c 'import os,sys;print(os.path.realpath(sys.argv[1]))' "$0")"; . "$(dirname "$SELF")/common.sh"
[ -f "$ON_FILE" ] || exit 0
TXT="$(printf '%s' "$HOOK" | MODE="$MODE" MAX="$MAX" python3 "$SCRIPTS_DIR/speak-reply.py")"
[ -n "$TXT" ] || exit 0
NORM="$(printf '%s' "$TXT" | tr -s '[:space:]' ' ')"
H="$(printf '%s' "$NORM" | shasum -a 256 | cut -c1-16)"
if [ -f "$LAST_FILE" ] && [ "$(cat "$LAST_FILE")" = "$H" ]; then exit 0; fi
exec bash "$SCRIPTS_DIR/speak-now.sh" "$NORM"
