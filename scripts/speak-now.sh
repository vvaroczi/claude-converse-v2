#!/usr/bin/env bash
# Speak a text right now. Usage: speak-now.sh "text"  |  -f file  |  --warm  |  --voice [name]
# Pocket speech goes through the voice daemon (model kept loaded, audio streamed), so it starts almost at once.
# Records a hash of what was spoken so the Stop hook does not repeat it at the end of the turn.
set -u
SELF="$(python3 -c 'import os,sys;print(os.path.realpath(sys.argv[1]))' "$0")"; . "$(dirname "$SELF")/common.sh"
if [ "${1:-}" = "--warm" ]; then
  # Start the daemon in the background and return at once; it is warm a few seconds later.
  [ "$ENGINE" = "pocket" ] && { nohup python3 "$SCRIPTS_DIR/voice-client.py" start >/dev/null 2>&1 & disown; }
  exit 0
fi
if [ "${1:-}" = "--audition" ]; then
  # converse-say --audition [names]  -> each voice says its name, one after another (default: all eight)
  shift; exec python3 "$SCRIPTS_DIR/voice-client.py" audition "$@"
fi
if [ "${1:-}" = "--voice" ]; then
  # converse-say --voice          -> print this chat's voice, e.g. "jean Jean"
  # converse-say --voice Cosette  -> this chat speaks as Cosette from now on
  exec python3 "$SCRIPTS_DIR/voice-client.py" voice ${2:+"$2"}
fi
[ -f "$ON_FILE" ] || exit 0
if [ "${1:-}" = "-f" ]; then TXT="$(cat "$2")"; else TXT="${1:-}"; fi
TXT="$(printf '%s' "$TXT" | sed -e 's/^[[:space:]]*🔊[[:space:]]*//' | tr -s '[:space:]' ' ')"
[ -n "$TXT" ] || exit 0
mkdir -p "$CONVERSE_HOME/last-spoken.d"
find "$CONVERSE_HOME/last-spoken.d" -type f -mtime +2 -delete 2>/dev/null
printf '%s' "$TXT" | shasum -a 256 | cut -c1-16 > "$LAST_FILE"
pkill -x say 2>/dev/null  # silence the macOS voice if it was speaking
case "$ENGINE" in
  pocket)
    if printf '%s' "$TXT" | python3 "$SCRIPTS_DIR/voice-client.py" say; then exit 0; fi
    # Daemon unavailable: fall back to the macOS voice rather than stay silent.
    ( printf '%s\n' "$TXT" | nohup say -v "$VOICE" -r "$RATE" >/dev/null 2>&1 ) & disown ;;
  say)
    ( printf '%s\n' "$TXT" | nohup say -v "$VOICE" -r "$RATE" >/dev/null 2>&1 ) & disown ;;
  *) exit 0 ;;
esac
exit 0
