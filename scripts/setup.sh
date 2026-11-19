#!/usr/bin/env bash
# One-time setup for converse2: a slim Python venv with mlx-audio (Pocket TTS only, no PyTorch),
# the Pocket model (about 230 MB) and the default config. About 340 MB to download, 680 MB on disk.
# Needs a Mac with Apple Silicon (Pocket runs on MLX). Safe to re-run.
set -eu
CONVERSE_HOME="${CONVERSE_HOME:-$HOME/.claude/converse2}"
mkdir -p "$CONVERSE_HOME/models" "$CONVERSE_HOME/bin"
SCRIPTS_DIR="$(cd "$(dirname "$0")" && pwd)"
if [ "$(uname -s)" != "Darwin" ] || [ "$(uname -m)" != "arm64" ]; then
  echo "converse2 needs a Mac with Apple Silicon (M1 or newer). Use converse v1 (Kokoro) elsewhere."; exit 1
fi
PY="$(command -v python3.12 || command -v python3.11 || command -v python3.10 || command -v python3.13 || command -v python3 || true)"
[ -n "$PY" ] || { echo "python3 (3.10 or newer) is required"; exit 1; }
"$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' || { echo "python3 is too old: 3.10 or newer is required"; exit 1; }
VPY="$CONVERSE_HOME/venv/bin/python"
if ! { [ -x "$VPY" ] && "$VPY" -c "import mlx_audio, sounddevice, audiotsm" 2>/dev/null; }; then
  echo "Creating the venv and installing mlx-audio for Pocket (about 110 MB, a minute or two)..."
  rm -rf "$CONVERSE_HOME/venv"
  "$PY" -m venv "$CONVERSE_HOME/venv"
  "$VPY" -m pip -q install --upgrade pip
  # mlx-audio's full dependency list pulls in PyTorch and transformers (over 1 GB) for models Pocket does not use.
  "$VPY" -m pip -q install --no-warn-conflicts --no-deps "mlx-audio==0.6.7"
  "$VPY" -m pip -q install --no-warn-conflicts "mlx>=0.30" "numpy>=2" "scipy" "sentencepiece" "tokenizers" "huggingface_hub" "requests" \
    "sounddevice>=0.5" "audiotsm==0.1.2"
fi
MODEL_DIR="$CONVERSE_HOME/models/pocket-tts"
if [ ! -s "$MODEL_DIR/model.safetensors" ]; then
  echo "Downloading the Pocket voice model (about 230 MB)..."
  "$VPY" -c "
from huggingface_hub import snapshot_download
snapshot_download('mlx-community/pocket-tts', local_dir='$MODEL_DIR')"
fi
[ -f "$CONVERSE_HOME/config" ] || cat > "$CONVERSE_HOME/config" <<CFG
ENGINE=pocket
KVOICE=alba
SPEED=1.0
SPEAK_LANG=en-us
PACE=normal
PERSONA=plain
USER_NAME=
MODE=marked
MAX=900
VOICE=Samantha
RATE=185
CFG
ln -sfn "$SCRIPTS_DIR/speak-now.sh" "$CONVERSE_HOME/bin/converse-say"
ln -sfn "$SCRIPTS_DIR/speak-stop.sh" "$CONVERSE_HOME/bin/converse-stop"
if [ -f "$HOME/.claude/converse/on" ]; then
  echo "Note: converse v1 is also switched on (~/.claude/converse/on). Run /converse off there, or replies are spoken twice."
fi
echo "Setup done. Test: $CONVERSE_HOME/bin/converse-say \"Conversation mode works.\" (after /converse2 on)"
