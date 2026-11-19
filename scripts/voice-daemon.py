#!/usr/bin/env python3
"""Converse2 voice daemon: keeps Pocket TTS loaded and streams its audio straight to the speakers,
so speech starts a few hundredths of a second after a sentence arrives.

Run with the converse2 venv python. Listens on $CONVERSE_HOME/voice.sock, one JSON request per connection:
  {"cmd": "say", "text": "...", "voice": "alba", "speed": 1.0, "source": "<chat id>", "label": "..."}
  {"cmd": "voice", "source": "...", "set": "Jean"}   {"cmd": "stop", "source": "..."}   {"cmd": "ping"}   {"cmd": "quit"}
Replies with one line ("ok" or "err ...") at once; speaking happens in the background.
Exits after CONVERSE_IDLE seconds (default 3600) with nothing said."""
import collections, json, os, re, shutil, socket, sys, threading, time

HOME = os.environ.get("CONVERSE_HOME") or os.path.expanduser("~/.claude/converse2")
SOCK = os.path.join(HOME, "voice.sock")
MODEL_DIR = os.path.join(HOME, "models", "pocket-tts")
IDLE = int(os.environ.get("CONVERSE_IDLE", "3600"))
STREAM_INTERVAL = 0.25   # seconds of audio per streamed piece
MUTE = bool(os.environ.get("CONVERSE_MUTE"))   # tests: play silence instead of speech
DEBUG = bool(os.environ.get("CONVERSE_DEBUG"))


def already_running():
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(0.5)
    try:
        s.connect(SOCK)
        s.sendall(b'{"cmd":"ping"}\n')
        return s.recv(16).startswith(b"ok")
    except OSError:
        return False
    finally:
        s.close()


if already_running():
    sys.exit(0)
# Loading takes a few seconds, so a second launch can arrive meanwhile ("--warm" then "say"): only one wins.
import fcntl  # noqa: E402
_lock = open(os.path.join(HOME, "daemon.lock"), "w")
try:
    fcntl.flock(_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
except OSError:
    sys.exit(0)

import numpy as np  # noqa: E402
import sounddevice as sd  # noqa: E402

# ---- Voices --------------------------------------------------------------------------------------
# Pocket's eight built-in voices. The first chat speaks in the configured voice; a new chat that starts
# while others are active gets the next one in POOL that no active chat uses, so you can tell chats
# apart by ear. "use Jean" in a chat pins that chat's voice. Kept in voices.json.
VOICES = ["alba", "azelma", "cosette", "eponine", "fantine", "javert", "jean", "marius"]
POOL = ["alba", "jean", "cosette", "marius", "fantine", "javert", "eponine", "azelma"]
DEFAULT_VOICE = "alba"


def voice_id(name):
    """Accept a voice by name in any case ("Jean", "jean"); None when Pocket has no such voice."""
    name = str(name or "").strip().lower()
    return name if name in VOICES else None


# ---- Playback ------------------------------------------------------------------------------------
class Player:
    """One output stream per spoken reply, fed from a queue of float32 pieces. clear() silences at once."""

    def __init__(self, sr):
        self.sr = sr
        self.lock = threading.Lock()
        self.buf = collections.deque()
        self.offset = 0          # samples already played from buf[0]
        self.pending = 0         # samples queued and not yet played
        self.stream = None
        self.first = None        # when the first audio of this reply was queued (for the debug log)

    def _callback(self, outdata, frames, _time, _status):
        out = outdata[:, 0]
        filled = 0
        with self.lock:
            while filled < frames and self.buf:
                head = self.buf[0]
                n = min(frames - filled, len(head) - self.offset)
                out[filled:filled + n] = head[self.offset:self.offset + n]
                filled += n
                self.offset += n
                self.pending -= n
                if self.offset >= len(head):
                    self.buf.popleft()
                    self.offset = 0
        out[filled:] = 0

    def open(self):
        self.first = None
        # A new stream per reply follows the current default output (headphones plugged in mid-session).
        self.stream = sd.OutputStream(samplerate=self.sr, channels=1, dtype="float32",
                                      callback=self._callback, latency="low")
        self.stream.start()

    def push(self, audio):
        if MUTE:
            audio = np.zeros_like(audio)
        if self.first is None:
            self.first = time.time()
        if len(audio):
            with self.lock:
                self.buf.append(audio)
                self.pending += len(audio)

    def clear(self):
        with self.lock:
            self.buf.clear()
            self.offset = 0
            self.pending = 0

    def busy(self):
        return self.pending > 0

    def close(self):
        s, self.stream = self.stream, None
        if s is not None:
            try:
                s.stop()
                s.close()
            except Exception:
                pass


class Stretcher:
    """Change the pace without changing the pitch (WSOLA), piece by piece as audio streams in.
    Pocket itself has no speed setting."""

    def __init__(self, speed):
        from audiotsm import wsola
        self.tsm = wsola(1, speed=speed)
        self.parts = []

    # audiotsm writer interface
    channels = 1

    def write(self, buffer):
        self.parts.append(np.array(buffer[0], dtype=np.float32))
        return buffer.shape[1]

    def _take(self):
        out = np.concatenate(self.parts) if self.parts else np.zeros(0, np.float32)
        self.parts = []
        return out

    def feed(self, audio):
        from audiotsm.io.array import ArrayReader
        reader = ArrayReader(audio.reshape(1, -1))
        finished = False
        while not (finished and reader.empty):
            self.tsm.read_from(reader)
            _, finished = self.tsm.write_to(self)
        return self._take()

    def finish(self):
        finished = False
        while not finished:
            _, finished = self.tsm.flush_to(self)
        return self._take()


def sentences(text):
    """Sentences, with very long ones broken at clause boundaries so the first sound comes quickly."""
    out = []
    for s in re.split(r"(?<=[.!?…])\s+", text):
        s = s.strip()
        if not s:
            continue
        if len(s) > 160:
            out.extend(p for p in re.split(r"(?<=[,;:—–])\s+", s) if p)
        else:
            out.append(s)
    return out


# ---- State shared between the socket thread and the speaking thread ------------------------------
VOICE_FILE = os.path.join(HOME, "voices.json")
ACTIVE_WINDOW = 12 * 3600
LABEL_WINDOW = 900
try:
    assigned = {s: v for s, v in json.load(open(VOICE_FILE)).items()
                if time.time() - v.get("seen", 0) < 7 * 86400 and v.get("voice") in VOICES}
except Exception:
    assigned = {}

state_lock = threading.Lock()
wake = threading.Condition(state_lock)
generation = 0          # bumped by every new job and every stop; a job that sees a change ends
pending = []            # jobs waiting: dicts with source, label, text, voice, speed
current = None          # job speaking now
last_source, last_end = None, 0.0
last_used = time.time()
player = None
ready = threading.Event()


def save_voices():
    try:
        tmp = VOICE_FILE + ".tmp"
        with open(tmp, "w") as f:
            json.dump(assigned, f)
        os.replace(tmp, VOICE_FILE)
    except OSError:
        pass


def voice_for(source, default):
    """The voice this chat speaks in; assigns one on first use (caller holds state_lock)."""
    now = time.time()
    default = voice_id(default) or DEFAULT_VOICE
    a = assigned.get(source)
    if a:
        a["seen"] = now
        save_voices()
        return a["voice"]
    in_use = {v["voice"] for s, v in assigned.items() if s != source and now - v.get("seen", 0) < ACTIVE_WINDOW}
    pick = default if default not in in_use else next((v for v in POOL if v not in in_use), default)
    assigned[source] = {"voice": pick, "pinned": False, "seen": now}
    save_voices()
    return pick


def cancel_current():
    """Stop what is speaking now (caller holds state_lock)."""
    global generation
    generation += 1
    if player:
        player.clear()


def speak(model, gen, text, voice, speed):
    """Generate sentence by sentence and push audio as it arrives; return when it has all been heard."""
    player.open()
    try:
        for sent in sentences(text):
            if gen != generation:
                return
            st = Stretcher(speed) if abs(speed - 1.0) >= 0.02 else None
            for r in model.generate(sent, voice=voice, stream=True, streaming_interval=STREAM_INTERVAL):
                if gen != generation:
                    return
                a = np.array(r.audio, dtype=np.float32).reshape(-1)
                player.push(st.feed(a) if st else a)   # each piece plays the moment it exists
            if st and gen == generation:
                player.push(st.finish())
        while player.busy() and gen == generation:
            time.sleep(0.02)
        time.sleep(0.12)  # let the device play out its last block
    finally:
        player.close()


def worker():
    """Owns the model: MLX work stays on this one thread."""
    global current, generation, last_source, last_end, player
    from mlx_audio.tts.utils import load_model
    model = load_model(MODEL_DIR)
    player = Player(getattr(model, "sample_rate", 24000))
    try:  # warm up: the first generation after load is several times slower than the rest
        for _ in model.generate("Ready.", voice=DEFAULT_VOICE):
            pass
    except Exception:
        pass
    ready.set()
    while True:
        with wake:
            while not pending:
                wake.wait()
            job = pending.pop(0)
            generation += 1
            gen = generation
            current = job
            prefix = ""
            if (job["label"] and last_source and last_source != job["source"]
                    and time.time() - last_end < LABEL_WINDOW):
                prefix = job["label"].rstrip(".") + ". "
        t0 = time.time()
        try:
            speak(model, gen, prefix + job["text"], job["voice"], job["speed"])
            note = (f"first {player.first - t0:.2f}s" if player.first else "no audio") + f" total {time.time() - t0:.2f}s"
        except Exception as e:
            note = f"error {type(e).__name__}: {e}"
        if DEBUG:
            with open(os.path.join(HOME, "voice-debug.log"), "a") as f:
                f.write(f"{t0:.2f} {job['source']} {job['voice']} x{job['speed']} {note} | {prefix + job['text']}\n")
        with wake:
            current = None
            last_source, last_end = job["source"], time.time()


def mine(job, source):
    """A job belongs to a chat when it came from it, including its auditions ("<chat>~<voice>")."""
    return job["source"] == source or job["source"].startswith(source + "~")


def handle(req):
    global last_used
    cmd = req.get("cmd")
    last_used = time.time()
    source = str(req.get("source") or "default")
    if cmd == "ping":
        return "ok"
    if cmd == "say":
        text = str(req.get("text") or "").strip()
        if not text:
            return "ok"
        job = {"source": source, "label": str(req.get("label") or "")[:40], "text": text,
               "speed": min(max(float(req.get("speed") or 1.0), 0.5), 2.0)}
        with wake:
            # "fixed": this exact voice for this one job (auditions), without assigning it to the chat.
            job["voice"] = voice_id(req.get("fixed")) or voice_for(source, req.get("voice"))
            pending[:] = [j for j in pending if j["source"] != source]
            if current and current["source"] == source:
                cancel_current()
                pending.insert(0, job)     # same chat: the new reply plays straight away
            else:
                pending.append(job)        # another chat is talking: wait for it
            wake.notify()
        return "ok"
    if cmd == "voice":
        # Which voice this chat speaks in (assigned now if it has none): "ok <id> <Name>". With "set": pin it.
        with wake:
            if req.get("set"):
                vid = voice_id(req["set"])
                if not vid:
                    return "err unknown voice (Pocket voices: " + ", ".join(v.capitalize() for v in VOICES) + ")"
                assigned[source] = {"voice": vid, "pinned": True, "seen": time.time()}
                save_voices()
            vid = voice_for(source, req.get("voice"))
        return f"ok {vid} {vid.capitalize()}"
    if cmd in ("stop", "quit"):
        # A stop that names no chat (plain `converse-stop`) stops everything.
        everyone = cmd == "quit" or req.get("all") or not req.get("source")
        with wake:
            if everyone:
                pending.clear()
            else:
                pending[:] = [j for j in pending if not mine(j, source)]
            if current and (everyone or mine(current, source)):
                cancel_current()
        if cmd == "quit":
            threading.Thread(target=shutdown, daemon=True).start()
        return "ok"
    return "err unknown command"


def shutdown():
    time.sleep(0.1)
    try:
        os.remove(SOCK)
    except OSError:
        pass
    os._exit(0)


def idle_watch():
    while True:
        time.sleep(30)
        if time.time() - last_used > IDLE and current is None and not pending:
            shutdown()


threading.Thread(target=worker, daemon=True).start()
if not ready.wait(120):
    sys.exit(1)
try:
    os.remove(SOCK)
except OSError:
    pass
server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
server.bind(SOCK)
os.chmod(SOCK, 0o600)
server.listen(8)
threading.Thread(target=idle_watch, daemon=True).start()
while True:
    conn, _ = server.accept()
    try:
        conn.settimeout(2)
        data = b""
        while not data.endswith(b"\n") and len(data) < 65536:
            part = conn.recv(8192)
            if not part:
                break
            data += part
        try:
            reply = handle(json.loads(data.decode("utf-8") or "{}"))
        except Exception as e:
            reply = "err " + type(e).__name__
        conn.sendall((reply + "\n").encode())
    except OSError:
        pass
    finally:
        conn.close()
