#!/usr/bin/env bash
# Stop speech at once. Runs on UserPromptSubmit, so whatever the person sends in a chat cuts that chat's voice
# (other chats keep their place in the queue).
# Usage: speak-stop.sh (this chat) | speak-stop.sh --all (every chat) | speak-stop.sh --quit (every chat, and the daemon exits)
# As a hook it reads the session from the hook JSON on stdin; run by hand it uses CLAUDE_CODE_SESSION_ID.
HOOK="$(python3 -c 'import sys, select
r = select.select([sys.stdin], [], [], 0.2)[0] if not sys.stdin.isatty() else []
print(sys.stdin.read() if r else "")' 2>/dev/null)"
if [ -n "$HOOK" ]; then
  SID="$(printf '%s' "$HOOK" | python3 -c 'import json,sys
try: print(json.load(sys.stdin).get("session_id") or "")
except Exception: print("")')"
  [ -n "$SID" ] && export CONVERSE_SOURCE="$SID"
fi
SELF="$(python3 -c 'import os,sys;print(os.path.realpath(sys.argv[1]))' "$0")"; . "$(dirname "$SELF")/common.sh"
case "${1:-}" in
  --quit) python3 "$SCRIPTS_DIR/voice-client.py" quit 2>/dev/null ;;
  --all)  python3 "$SCRIPTS_DIR/voice-client.py" stop --all 2>/dev/null ;;
  *)      python3 "$SCRIPTS_DIR/voice-client.py" stop 2>/dev/null ;;
esac
pkill -x say 2>/dev/null
exit 0
