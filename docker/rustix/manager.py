"""
Rustix multi-bot manager.

Runs every bot folder as its own supervised process, with its own venv and
its own .env, and serves a web panel on the server's allocated port.

- A bot is any folder (inside BOTS_DIR) with one of BOT_ENTRIES in it.
- A `.disabled` file in a bot folder stops it from auto-starting.
- Crashed bots restart with backoff (5s doubling to 5m) when AUTO_RESTART=1.
- The Pterodactyl console accepts commands too: type `help`.
"""

import hmac
import os
import re
import secrets
import signal
import subprocess
import sys
import threading
import time
from collections import deque
from datetime import timedelta
from pathlib import Path

import psutil
from dotenv import dotenv_values
from flask import Flask, abort, jsonify, request, send_file, session

sys.path.insert(0, str(Path(__file__).resolve().parent))
from deps import ensure_venv  # noqa: E402

HERE = Path(__file__).resolve().parent


def env_on(name, default="1"):
    return os.environ.get(name, default).strip().lower() in ("1", "true", "yes", "on")


HOME = Path(os.environ.get("RUSTIX_HOME", "/home/container"))
BOTS_DIR = (HOME / os.environ.get("BOTS_DIR", "").strip().strip("/")).resolve()
STATE_DIR = HOME / ".rustix"
LOG_DIR = HOME / "logs"
ENTRIES = os.environ.get("BOT_ENTRIES", "bot.py main.py app.py").split()
AUTO_RESTART = env_on("AUTO_RESTART")
MIRROR = env_on("CONSOLE_MIRROR")
PORT = int(os.environ.get("SERVER_PORT") or os.environ.get("PORT") or 8080)
EXCLUDED = {"logs", "__pycache__", "node_modules", "venv", "env", "backup-dont-touch"}
# Never hand these to bot processes: panel/git secrets and egg plumbing.
SCRUB = {"PANEL_PASSWORD", "ACCESS_TOKEN", "USERNAME", "GIT_ADDRESS", "STARTUP", "MULTI_BOT"}
LOG_MAX_BYTES = 5 * 1024 * 1024
ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")

ORANGE, RESET = "\033[38;5;208m", "\033[0m"
_console_lock = threading.Lock()


def say(msg):
    with _console_lock:
        print(f"{ORANGE}[rustix]{RESET} {msg}", flush=True)


class Bot:
    def __init__(self, path: Path):
        self.id = path.name
        self.name = path.name.replace("-", " ").replace("_", " ").title()
        self.dir = path
        self.lines = deque(maxlen=1000)
        self.seq = 0
        self.proc = None
        self.started_at = None
        self.state = "stopped"
        self.wanted = False
        self.restarts = 0
        self.last_exit = None
        self.next_try = None
        self.lock = threading.RLock()
        self.wake = threading.Event()
        self.thread = None
        self._ps = {}
        self.log_path = LOG_DIR / f"{self.id}.log"

    # ---- info ------------------------------------------------------------
    @property
    def autostart(self):
        return not (self.dir / ".disabled").exists()

    @property
    def entry(self):
        return next((e for e in ENTRIES if (self.dir / e).is_file()), None)

    def usage(self):
        proc = self.proc
        if not proc or proc.poll() is not None:
            self._ps = {}
            return 0.0, 0
        cpu, mem, seen = 0.0, 0, {}
        try:
            root = self._ps.get(proc.pid) or psutil.Process(proc.pid)
            for p in [root] + root.children(recursive=True):
                p = self._ps.get(p.pid, p)
                seen[p.pid] = p
                try:
                    cpu += p.cpu_percent(None)
                    mem += p.memory_info().rss
                except psutil.Error:
                    pass
        except psutil.Error:
            pass
        self._ps = seen
        return round(cpu, 1), mem

    def info(self):
        cpu, mem = self.usage()
        return {
            "id": self.id,
            "name": self.name,
            "state": self.state,
            "autostart": self.autostart,
            "entry": self.entry,
            "uptime": int(time.time() - self.started_at) if self.started_at else 0,
            "restarts": self.restarts,
            "last_exit": self.last_exit,
            "retry_in": max(0, int(self.next_try - time.time())) if self.state == "backoff" and self.next_try else None,
            "cpu": cpu,
            "mem": mem,
            "seq": self.seq,
        }

    # ---- logging ---------------------------------------------------------
    def log(self, line):
        raw, line = line, ANSI.sub("", line)
        with self.lock:
            self.seq += 1
            self.lines.append((self.seq, line))
            try:
                if self.log_path.exists() and self.log_path.stat().st_size > LOG_MAX_BYTES:
                    self.log_path.replace(self.log_path.with_suffix(".log.1"))
                with open(self.log_path, "a", encoding="utf-8", errors="replace") as f:
                    f.write(line + "\n")
            except OSError:
                pass
        if MIRROR:
            with _console_lock:
                print(f"[{self.id}] {raw}", flush=True)

    def tail(self, after=0):
        with self.lock:
            return [{"n": n, "t": t} for n, t in self.lines if n > after]

    # ---- lifecycle -------------------------------------------------------
    def child_env(self):
        env = {k: v for k, v in os.environ.items() if k not in SCRUB and not k.startswith("RUSTIX_")}
        dotenv = self.dir / ".env"
        if dotenv.is_file():
            env.update({k: v for k, v in dotenv_values(dotenv).items() if v is not None})
        venv = self.dir / ".venv"
        env.update(
            VIRTUAL_ENV=str(venv),
            PATH=f"{venv / 'bin'}:{env.get('PATH', '/usr/local/bin:/usr/bin:/bin')}",
            PYTHONUNBUFFERED="1",
            RUSTIX_BOT=self.id,
        )
        return env

    def start(self):
        with self.lock:
            self.wanted = True
            self.wake.set()
            if self.thread and self.thread.is_alive():
                return
            self.thread = threading.Thread(target=self._supervise, name=f"bot-{self.id}", daemon=True)
            self.thread.start()

    def _supervise(self):
        backoff = 0
        while self.wanted:
            self.wake.clear()
            entry = self.entry
            if not entry:
                self.log(f"[rustix] no entry file found (looked for {', '.join(ENTRIES)})")
                self.state, self.wanted = "crashed", False
                break
            self.state = "installing"
            try:
                py = ensure_venv(self.dir, self.dir / ".venv", "requirements.txt", "", log=self.log)
            except Exception as e:  # keep the panel alive whatever pip does
                self.log(f"[rustix] dependency setup failed: {e}")
                py = None
            with self.lock:
                if not self.wanted:
                    break
                if py:
                    self.log(f"[rustix] starting {entry}")
                    self.proc = subprocess.Popen(
                        [str(py), "-u", entry],
                        cwd=str(self.dir),
                        env=self.child_env(),
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                        errors="replace",
                        bufsize=1,
                        start_new_session=True,
                    )
                    self.started_at = time.time()
                    self.state = "running"
            ran = 0
            if py:
                proc = self.proc
                for line in proc.stdout:
                    self.log(line.rstrip("\n"))
                rc = proc.wait()
                ran = time.time() - self.started_at
                with self.lock:
                    self.proc, self.started_at, self.last_exit = None, None, rc
                if not self.wanted:
                    break
                self.log(f"[rustix] exited with code {rc}")
                if rc == 0:
                    self.wanted = False
                    break
            if not AUTO_RESTART:
                self.state, self.wanted = "crashed", False
                break
            backoff = 5 if ran > 60 or not backoff else min(backoff * 2, 300)
            self.restarts += 1
            self.state, self.next_try = "backoff", time.time() + backoff
            self.log(f"[rustix] restarting in {backoff}s")
            self.wake.wait(backoff)
        if self.state != "crashed":
            self.state = "stopped"

    def stop(self, wait=True):
        with self.lock:
            self.wanted = False
            self.wake.set()
            proc = self.proc
        if proc and proc.poll() is None:
            self.log("[rustix] stopping")
            for sig, grace in ((signal.SIGINT, 8), (signal.SIGTERM, 4), (signal.SIGKILL, 2)):
                try:
                    os.killpg(proc.pid, sig)
                except (ProcessLookupError, PermissionError):
                    break
                try:
                    proc.wait(timeout=grace)
                    break
                except subprocess.TimeoutExpired:
                    continue
        if wait and self.thread and self.thread is not threading.current_thread():
            self.thread.join(timeout=20)
        self.state = "stopped"

    def restart(self):
        self.stop()
        self.start()

    def reinstall(self):
        self.stop()
        (self.dir / ".venv" / ".rustix-deps").unlink(missing_ok=True)
        self.start()

    def set_autostart(self, on):
        flag = self.dir / ".disabled"
        if on:
            flag.unlink(missing_ok=True)
        else:
            flag.touch()


# ---- registry ----------------------------------------------------------------
BOTS: dict[str, Bot] = {}
_reg_lock = threading.Lock()


def discover():
    found = []
    if not BOTS_DIR.is_dir():
        return found
    for d in sorted(BOTS_DIR.iterdir()):
        if d.is_dir() and not d.name.startswith(".") and d.name not in EXCLUDED:
            if any((d / e).is_file() for e in ENTRIES):
                found.append(d)
    return found


def rescan():
    with _reg_lock:
        paths = {p.name: p for p in discover()}
        for name, p in paths.items():
            if name not in BOTS:
                BOTS[name] = Bot(p)
                say(f"found bot: {name}")
        for name in list(BOTS):
            if name not in paths and BOTS[name].state == "stopped":
                del BOTS[name]
                say(f"bot removed: {name}")


def _rescan_loop():
    while True:
        time.sleep(10)
        try:
            rescan()
        except Exception as e:
            say(f"rescan failed: {e}")


def do_action(bot: Bot, action: str):
    actions = {
        "start": bot.start,
        "stop": lambda: threading.Thread(target=bot.stop, daemon=True).start(),
        "restart": lambda: threading.Thread(target=bot.restart, daemon=True).start(),
        "reinstall": lambda: threading.Thread(target=bot.reinstall, daemon=True).start(),
        "enable": lambda: bot.set_autostart(True),
        "disable": lambda: bot.set_autostart(False),
    }
    if action not in actions:
        return False
    actions[action]()
    return True


# ---- panel auth ----------------------------------------------------------------
def _secret(name, make):
    STATE_DIR.mkdir(exist_ok=True)
    f = STATE_DIR / name
    if f.exists() and f.read_text().strip():
        return f.read_text().strip(), False
    value = make()
    f.write_text(value)
    f.chmod(0o600)
    return value, True


def panel_password():
    pw = os.environ.get("PANEL_PASSWORD", "").strip()
    if not pw and (HOME / ".env").is_file():  # old panel.py kept it in the root .env
        pw = (dotenv_values(HOME / ".env").get("PANEL_PASSWORD") or "").strip()
    if pw:
        return pw, "from the Panel Password variable"
    pw, _ = _secret("panel-password", lambda: secrets.token_urlsafe(12))
    return pw, "generated; set the Panel Password variable to pick your own"


PASSWORD, PASSWORD_SOURCE = panel_password()
app = Flask(__name__)
app.secret_key, _ = _secret("secret.key", lambda: secrets.token_hex(32))
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Strict",
    PERMANENT_SESSION_LIFETIME=timedelta(days=7),
)
_fails: dict[str, list[float]] = {}


def authed():
    return session.get("pw") == hmac.new(app.secret_key.encode(), PASSWORD.encode(), "sha256").hexdigest()


@app.before_request
def guard():
    p = request.path
    if p in ("/", "/healthz", "/api/login") or p.startswith("/static"):
        return
    if not authed():
        abort(401)
    if request.method == "POST" and request.headers.get("X-CSRF") != session.get("csrf"):
        abort(403)


@app.after_request
def headers(resp):
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Referrer-Policy"] = "no-referrer"
    return resp


@app.get("/")
def index():
    return send_file(HERE / "panel.html")


@app.get("/healthz")
def healthz():
    return "ok"


@app.post("/api/login")
def login():
    ip = request.headers.get("X-Forwarded-For", request.remote_addr or "?").split(",")[0].strip()
    now = time.time()
    recent = [t for t in _fails.get(ip, []) if now - t < 300]
    if len(recent) >= 10:
        return jsonify(error="Too many attempts, wait a few minutes"), 429
    given = ((request.get_json(silent=True) or {}).get("password") or "").encode()
    if not hmac.compare_digest(given, PASSWORD.encode()):
        _fails[ip] = recent + [now]
        return jsonify(error="Wrong password"), 401
    _fails.pop(ip, None)
    session.permanent = True
    session["pw"] = hmac.new(app.secret_key.encode(), PASSWORD.encode(), "sha256").hexdigest()
    session["csrf"] = secrets.token_urlsafe(24)
    return jsonify(ok=True)


@app.post("/api/logout")
def logout():
    session.clear()
    return jsonify(ok=True)


@app.get("/api/state")
def state():
    bots = [b.info() for b in list(BOTS.values())]
    me = psutil.Process()
    return jsonify(
        csrf=session.get("csrf"),
        python=sys.version.split()[0],
        manager_mem=me.memory_info().rss,
        mem_limit=_mem_limit(),
        bots=bots,
    )


@app.get("/api/bots/<bot_id>/logs")
def logs(bot_id):
    bot = BOTS.get(bot_id) or abort(404)
    return jsonify(seq=bot.seq, lines=bot.tail(request.args.get("after", 0, type=int)))


@app.post("/api/bots/<bot_id>/<action>")
def bot_action(bot_id, action):
    bot = BOTS.get(bot_id) or abort(404)
    return jsonify(ok=True) if do_action(bot, action) else abort(400)


@app.post("/api/all/<action>")
def all_action(action):
    if action not in ("start", "stop", "restart"):
        abort(400)
    for bot in list(BOTS.values()):
        do_action(bot, action)
    return jsonify(ok=True)


@app.post("/api/rescan")
def api_rescan():
    rescan()
    return jsonify(ok=True)


def _mem_limit():
    try:
        raw = Path("/sys/fs/cgroup/memory.max").read_text().strip()
        return None if raw == "max" else int(raw)
    except (OSError, ValueError):
        return None


# ---- console commands --------------------------------------------------------
HELP = """commands:
  list                         show every bot and its state
  start|stop|restart <bot|all>
  reinstall <bot>              force a fresh dependency install
  enable|disable <bot>         toggle auto-start (.disabled file)
  logs <bot> [lines]           print recent output
  rescan                       look for new bot folders
  password                     show the web panel password"""


def console_loop():
    for raw in sys.stdin:
        parts = raw.strip().split()
        if not parts:
            continue
        cmd, args = parts[0].lower(), parts[1:]
        if cmd in ("help", "?"):
            say(HELP)
        elif cmd in ("list", "ls", "status"):
            for b in BOTS.values():
                i = b.info()
                say(f"{i['id']:<28} {i['state']:<10} cpu {i['cpu']:>5}%  mem {i['mem'] // 1048576:>4} MB"
                    f"  {'' if i['autostart'] else '(auto-start off)'}")
        elif cmd == "rescan":
            rescan()
        elif cmd == "password":
            say(f"panel password: {PASSWORD}")
        elif cmd == "logs" and args:
            b = BOTS.get(args[0])
            n = int(args[1]) if len(args) > 1 and args[1].isdigit() else 30
            with _console_lock:
                for line in (b.tail()[-n:] if b else []):
                    print(f"[{b.id}] {line['t']}", flush=True)
        elif cmd in ("start", "stop", "restart") and args and args[0] == "all":
            for b in list(BOTS.values()):
                do_action(b, cmd)
        elif args and args[0] in BOTS and do_action(BOTS[args[0]], cmd):
            say(f"{cmd} {args[0]}")
        else:
            say(f"unknown command or bot: {raw.strip()} (type 'help')")


# ---- main --------------------------------------------------------------------
def shutdown(*_):
    say("shutting down all bots")
    threads = [threading.Thread(target=b.stop) for b in BOTS.values()]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=25)
    os._exit(0)


def main():
    LOG_DIR.mkdir(exist_ok=True)
    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    rescan()
    if not BOTS:
        say(f"no bots yet: add a folder to {BOTS_DIR} with a {ENTRIES[0]} inside it")
    for b in BOTS.values():
        if b.autostart:
            b.start()
        else:
            say(f"{b.id}: auto-start is off")
    threading.Thread(target=_rescan_loop, daemon=True).start()
    threading.Thread(target=console_loop, daemon=True).start()
    say(f"panel password: {PASSWORD} ({PASSWORD_SOURCE})")
    say(f"Launching web panel on port {PORT}")

    import logging
    from waitress import serve
    logging.getLogger("waitress").setLevel(logging.ERROR)
    serve(app, host="0.0.0.0", port=PORT, threads=8, ident="rustix")


if __name__ == "__main__":
    main()
