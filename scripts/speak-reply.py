#!/usr/bin/env python3
"""Pick what to speak from the just-finished Claude Code turn.
Reads the Stop hook JSON on stdin, prints the text to speak (or nothing).
Rule: paragraphs that start with the speaker mark (U+1F50A, the loudspeaker emoji) anywhere in this turn's
assistant text are the spoken part, in order. Without any mark: MODE=marked speaks nothing,
MODE=recap speaks the turn's wrap-up recap (else the start of the reply), MODE=full speaks the reply up to MAX chars."""
import sys, json, re, os
MARK = "\U0001F50A"
mode = os.environ.get("MODE", "marked")
mx = int(os.environ.get("MAX", "900"))
try:
    hook = json.loads(sys.stdin.read() or "{}")
except Exception:
    sys.exit(0)
path = hook.get("transcript_path")
if not path or not os.path.exists(path):
    sys.exit(0)
rows = []
for line in open(path, encoding="utf-8", errors="ignore"):
    try:
        rows.append(json.loads(line))
    except Exception:
        pass
last_human = -1
for i, d in enumerate(rows):
    if d.get("type") != "user":
        continue
    c = d.get("message", {}).get("content")
    if isinstance(c, str):
        last_human = i
    elif isinstance(c, list) and c and all(isinstance(x, dict) and x.get("type") == "text" for x in c):
        last_human = i
texts, recap = [], None
for d in rows[last_human + 1:]:
    if d.get("type") != "assistant":
        continue
    for c in d.get("message", {}).get("content", []):
        if not isinstance(c, dict):
            continue
        if c.get("type") == "text" and c.get("text", "").strip():
            texts.append(c["text"])
        if c.get("type") == "tool_use" and str(c.get("name", "")).endswith("wrap_up"):
            r = (c.get("input") or {}).get("recap")
            if r:
                recap = r
marked = []
for t in texts:
    for para in re.split(r"\n\s*\n", t):
        p = para.strip()
        if p.startswith(MARK):
            marked.append(p[len(MARK):].strip())
if marked:
    text = " ".join(marked)
elif mode == "recap":
    text = recap or (texts[-1] if texts else "")
elif mode == "full":
    text = texts[-1] if texts else ""
else:
    text = ""
if not text:
    sys.exit(0)
text = re.sub(r"```.*?```", " code block. ", text, flags=re.S)
text = re.sub(r"`([^`]*)`", r"\1", text)
text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
text = re.sub(r"https?://\S+", "link", text)
text = re.sub(r"[*_#>|]+", " ", text)
text = re.sub(r"^\s*[-+]\s+", "", text, flags=re.M)
text = re.sub(r"\s+", " ", text).strip()
if len(text) > mx:
    cut = text[:mx]
    text = cut[:cut.rfind(". ") + 1] if ". " in cut else cut
print(text)
