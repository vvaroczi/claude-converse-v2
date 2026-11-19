#!/usr/bin/env python3
"""Talk to the converse2 voice daemon. Uses the system python3 (no venv needed).
  voice-client.py say      (text on stdin; voice/speed from env KVOICE, SPEED)
  voice-client.py voice [name]  (print this chat's voice, or pin it: "Jean", "cosette")
  voice-client.py audition [names]  (each voice says its name, one after another; default: all eight)
  voice-client.py stop [--all]   (this chat's speech only, unless --all)
  voice-client.py ping | quit
  voice-client.py start    (start the daemon if needed and wait until it is warm)
`say` and `start` launch the daemon when it is not running. Exit 0 when the daemon took the request, 1 otherwise."""
import json, os, socket, subprocess, sys, time

HOME = os.environ.get("CONVERSE_HOME") or os.path.expanduser("~/.claude/converse2")
SOCK = os.path.join(HOME, "voice.sock")
HERE = os.path.dirname(os.path.realpath(__file__))
VENV_PY = os.path.join(HOME, "venv", "bin", "python")


def send(req, timeout=1.0):
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect(SOCK)
        s.sendall((json.dumps(req) + "\n").encode())
        reply = s.recv(256).decode().strip()
        if req.get("cmd") == "voice":
            print(reply[3:] if reply.startswith("ok") else reply[4:])
        return reply.startswith("ok")
    except OSError:
        return False
    finally:
        s.close()


def launch(wait=45.0):  # loading Pocket takes a few seconds, longer on the very first run
    if not os.path.exists(VENV_PY):
        return False
    subprocess.Popen([VENV_PY, os.path.join(HERE, "voice-daemon.py")], stdin=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    end = time.time() + wait
    while time.time() < end:
        time.sleep(0.05)
        if send({"cmd": "ping"}, 0.3):
            return True
    return False


# Which chat is speaking: CONVERSE_SOURCE (set by the hooks), else the Claude Code session id.
SOURCE = os.environ.get("CONVERSE_SOURCE") or os.environ.get("CLAUDE_CODE_SESSION_ID") or "default"
LABEL = os.environ.get("CONVERSE_LABEL", "")

cmd = sys.argv[1] if len(sys.argv) > 1 else "ping"
if cmd == "say":
    req = {"cmd": "say", "text": sys.stdin.read(), "voice": os.environ.get("KVOICE", "alba"),
           "speed": float(os.environ.get("SPEED", "1.0") or 1.0), "source": SOURCE, "label": LABEL}
    ok = send(req) or (launch() and send(req))
elif cmd == "audition":
    names = sys.argv[2:] or ["alba", "cosette", "fantine", "eponine", "azelma", "jean", "javert", "marius"]
    speed = float(os.environ.get("SPEED", "1.0") or 1.0)
    ok = send({"cmd": "ping"}, 0.3) or launch()
    for n in names:
        n = n.strip().lower()
        ok = send({"cmd": "say", "text": f"This is {n.capitalize()}.", "fixed": n, "speed": speed,
                   "source": f"{SOURCE}~{n}", "label": ""}) and ok
elif cmd == "start":
    ok = send({"cmd": "ping"}, 0.3) or launch()
elif cmd == "voice":
    # voice-client.py voice [name]: print this chat's voice ("jean Jean"), or pin it to another
    req = {"cmd": "voice", "source": SOURCE, "voice": os.environ.get("KVOICE", "alba")}
    if len(sys.argv) > 2:
        req["set"] = sys.argv[2]
    ok = send(req) or (launch() and send(req))
elif cmd == "stop":
    ok = send({"cmd": "stop", "source": SOURCE, "all": "--all" in sys.argv}, 0.5)
else:
    ok = send({"cmd": cmd}, 0.5)
sys.exit(0 if ok else 1)
