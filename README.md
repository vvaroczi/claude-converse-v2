# converse2: Claude talks back, with Pocket

v2 of [converse](https://github.com/vvaroczi/claude-converse): the same conversation mode for Claude Code, with a faster local voice. Claude answers out loud without reading you every line.

What changed from v1: the voice is [Pocket TTS](https://huggingface.co/kyutai/pocket-tts) (Kyutai) running on Apple's MLX, instead of Kokoro. Pocket streams its audio, so speech starts a few hundredths of a second after a sentence reaches the voice, while the reply is still printing. Everything else works the same.

- `/converse2` on, `/converse2 off`. Nothing speaks unless the mode is on.
- Each reply opens with a short spoken part. Long breakdowns, tables and paths stay written for you to read.
- Send anything, even one letter, and the voice stops at once.
- Pick a voice by talking ("use Jean", "try Cosette") and set the pace ("faster", "quick fire", "take your time").
- Runs fully on your Mac. No API key, no audio leaves the machine. Falls back to the macOS voice if the model is missing.

## Install

```bash
claude plugin marketplace add vvaroczi/claude-converse-v2
claude plugin install converse2@converse2-marketplace
```

Then in any Claude Code session:

```
/converse2 setup     # once: about 340 MB to download, 680 MB on disk
/converse2           # talk
```

v1 and v2 keep their settings in separate folders (`~/.claude/converse` and `~/.claude/converse2`), so both can be installed. Switch on only one at a time, or replies are spoken twice.

## Size and speed
Measured on an M5 MacBook Air (16 GB):

| | converse v1 (Kokoro) | converse2 (Pocket) |
|---|---|---|
| Download | about 510 MB | about 340 MB (110 MB software, 230 MB model) |
| On disk | about 510 MB | about 680 MB |
| First sound after a sentence | about 0.3 s (whole sentence made first) | about 0.1 s (streams in quarter-second pieces) |
| Speed of generation | about 19 times real time | about 11 times real time |
| Memory while speaking | about 1.9 GB | under 1 GB |
| Languages | English plus 7 native | English; others use the macOS voice |
| Runs on | macOS, Linux | Apple Silicon Macs |

The slim install leaves out the PyTorch and transformers packages that mlx-audio would otherwise pull in (over 1 GB): Pocket does not use them.

## Talking to it (cheat sheet)
Once the mode is on, these work by voice or typed:

| Say or type | What happens |
|---|---|
| anything at all, even "stop" | the voice stops at once |
| "faster", "slower", "quick fire", "take your time", "normal pace" | pace: speed and how long the spoken part is |
| "play the voices" | the eight voices, each says its name; then pick |
| "use Jean", "use Cosette", or `/converse2 voice marius` | switch voice |
| "speed one point two" or `/converse2 speed 1.2` | speed alone |
| "longer answers" / "shorter answers" | spoken part grows or shrinks |
| "read the detail" | the written part of the last reply, read once |
| "be my coach", "talk like a butler", `/converse2 personality noir` | a personality (coach, butler, noir, grandma, pirate, hype, zen) or a mind (einstein, feynman, musk, jobs, munger, holmes); "drop the act" for plain |
| "converse off" | mode off, silent written replies |

`/converse2 help` prints this list; `/converse2 status` shows the current voice and pace.

## Voices
Pocket ships eight voices. Women: `alba` (default), `cosette`, `fantine`, `eponine`, `azelma`. Men: `jean`, `javert`, `marius`. Say "play the voices" to hear them all. Pocket has no speed setting of its own; the daemon changes the pace as the audio streams (WSOLA time stretching), so the pitch stays the same.

## Personalities
Same facts, different delivery. A personality changes how the spoken paragraph is phrased and which voice says it; the written detail stays plain and the numbers never change. Say "be my coach" or `/converse2 personality coach`, "drop the act" to go back.

- `coach`, the sadistic gym coach: "Three files. That's a warm-up, champ. Tests next. Go. Go. Go."
- `butler`, the unflappable British butler: "The tests have passed, sir. I took the liberty of fixing the typo they were complaining about."
- `noir`, the 1940s detective narrator: "The bug had been hiding in the parser all along. They always are."
- `grandma`, your worried grandmother: "The tests pass, love. Now go and eat something."
- `pirate`: "Arr, the build be green, me hearty. Three bugs walked the plank."
- `hype`, the stadium announcer: "Ladies and gentlemen... the tests... have passed!"
- `zen`, the monk: "The bug was a missing comma. Small things carry the weight."

Each one comes with a matching voice and speed. Adding your own is one table row in `skills/converse2/SKILL.md`.

### Minds
A mind is a personality plus a way of thinking: it reframes your problem the way that person would, asks their question, pushes back where they would. Like having them at the table. "Bring in Einstein", "think like Musk", `/converse2 personality feynman`.

- `einstein`: thought experiment first, strip it to the simplest form, distrust the shared assumption.
- `feynman`: explain it to a twelve-year-old or admit you do not understand it; name the one experiment that settles it.
- `musk` (in the spirit of his public engineering method): first principles, question every requirement, delete the part, then simplify.
- `jobs` (in the spirit of his public product method): start from the experience, say no, is it insanely great.
- `munger`: invert, always invert; incentives explain most things.
- `holmes` (fiction): observe before you theorise, the detail nobody mentioned is the case.

Real people are played in the spirit of their well-known public methods and manner, with no invented quotes. The voices are Pocket's stock voices, not clones.

## Languages
Pocket speaks English. `/converse2 language es` (or "speak Spanish") switches the spoken part to the macOS system voice for that language, which sounds plainer; switching back to English returns to Pocket. For native neural voices in Spanish, French, Italian, Portuguese, Hindi, Japanese or Mandarin, use converse v1.

## Requirements
- A Mac with Apple Silicon (M1 or newer)
- Python 3.10 or newer
- Claude Code 2.1 or newer (hooks: Stop, UserPromptSubmit)

## Several chats at once
Run conversation mode in as many Claude Code sessions as you like. They share one voice and take turns: a reply from another chat waits until the current one finishes, and when the voice switches chats it says which one first ("uxsimulatr chat."). Each chat gets its own voice. A chat's newer reply replaces its own older one, so nothing stale piles up. Typing in a chat stops only that chat; `converse-stop --all` silences everything.

## It knows your name
On first use it asks what to call you (or say "call me Sam"). Replies stay short and human: it uses your name when it greets you or comes back with news, not in every sentence.

## How it works
- `hooks/hooks.json` wires two hooks: Stop reads the 🔊 paragraphs of the finished reply; UserPromptSubmit cuts this chat's speech.
- The `converse2` skill tells Claude how to answer in the mode: spoken part first, written detail second, and how to trigger speech before the text lands (`~/.claude/converse2/bin/converse-say`), with a hash so the end-of-turn hook does not repeat it.
- `scripts/voice-daemon.py` keeps Pocket loaded on a local socket (`~/.claude/converse2/voice.sock`). For each reply it generates sentence by sentence and pushes each quarter-second of audio to one output stream the moment it exists, so there are no gaps and no waiting for a whole sentence. It exits after an hour unused. `scripts/voice-client.py` talks to it and starts it when needed.
- If the daemon can't start, the macOS voice speaks instead.
- State and the model live in `~/.claude/converse2/`, never inside the plugin, so updates keep your voice and pace.

## Licences
Plugin code: MIT. Pocket TTS weights: CC-BY-4.0 (Kyutai), MLX conversion by mlx-community. mlx-audio: MIT. The model is downloaded from Hugging Face at setup time, not bundled.

## About
A personal side project, shared in case it helps. v1 made Claude talk back; v2 makes it start talking sooner.
