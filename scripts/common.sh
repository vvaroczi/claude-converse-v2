# Shared settings for the converse2 scripts. State lives outside the plugin so updates keep it.
# Its own folder (not ~/.claude/converse), so converse v1 and v2 can be installed side by side.
CONVERSE_HOME="${CONVERSE_HOME:-$HOME/.claude/converse2}"
ON_FILE="$CONVERSE_HOME/on"
CONFIG_FILE="$CONVERSE_HOME/config"
VENV_PY="$CONVERSE_HOME/venv/bin/python"
SCRIPTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENGINE=pocket; KVOICE=alba; SPEED=1.0; SPEAK_LANG=en-us; VOICE=Samantha; RATE=185; MODE=marked; MAX=900; PACE=normal; PERSONA=plain; USER_NAME=
[ -f "$CONFIG_FILE" ] && . "$CONFIG_FILE"
if [ "$ENGINE" = "pocket" ] && [ ! -x "$VENV_PY" ]; then
  if command -v say >/dev/null 2>&1; then ENGINE=say; else ENGINE=none; fi
fi
# Pocket speaks English only. Other languages go to a macOS voice for that language (SAY_VOICE in the config wins).
case "$SPEAK_LANG" in
  en*) ;;
  *) if [ "$ENGINE" = "pocket" ] && command -v say >/dev/null 2>&1; then
       ENGINE=say
       _l2="$(printf '%s' "$SPEAK_LANG" | cut -c1-2 | tr 'A-Z' 'a-z')"
       VOICE="${SAY_VOICE:-$(say -v '?' 2>/dev/null | awk -v l="$_l2" 'match($0, / [a-z][a-z]_[A-Z][A-Z] /){n=substr($0,1,RSTART-1); sub(/ +$/,"",n); if(substr($0,RSTART+1,2)==l){print n; exit}}')}"
       [ -n "$VOICE" ] || VOICE=Samantha
     fi ;;
esac
# Which chat this is: set by the hooks (CONVERSE_SOURCE), else the Claude Code session running the command.
CONVERSE_SOURCE="$(printf '%s' "${CONVERSE_SOURCE:-${CLAUDE_CODE_SESSION_ID:-default}}" | tr -cd 'A-Za-z0-9_-' | cut -c1-64)"
[ -n "$CONVERSE_SOURCE" ] || CONVERSE_SOURCE=default
# What the voice calls this chat when it takes over from another one: the project folder's name.
if [ -z "${CONVERSE_LABEL:-}" ]; then
  _dir="${CONVERSE_CWD:-$PWD}"
  _top="$(git -C "$_dir" rev-parse --show-toplevel 2>/dev/null || printf '%s' "$_dir")"
  CONVERSE_LABEL="$(basename "$_top" | tr '_-' '  ') chat"
fi
# What this chat last spoke, so its end-of-turn hook does not repeat it. One file per chat.
LAST_FILE="$CONVERSE_HOME/last-spoken.d/$CONVERSE_SOURCE"
export CONVERSE_HOME CONVERSE_SOURCE CONVERSE_LABEL KVOICE SPEED SPEAK_LANG
