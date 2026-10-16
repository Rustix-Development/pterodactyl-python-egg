# Python Egg

[![Latest release](https://img.shields.io/github/v/release/Rustix-Development/pterodactyl-python-egg?label=egg)](https://github.com/Rustix-Development/pterodactyl-python-egg/releases/latest)
[![Build images](https://github.com/Rustix-Development/pterodactyl-python-egg/actions/workflows/build-images.yml/badge.svg)](https://github.com/Rustix-Development/pterodactyl-python-egg/actions/workflows/build-images.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

A [Pterodactyl](https://pterodactyl.io) egg for Python apps and Discord bots, on
**Python 3.11, 3.12, 3.13, 3.14 and 3.15**.

- **Fast installs**: `requirements.txt` is installed with [uv](https://github.com/astral-sh/uv)
  into a venv (falls back to pip if uv can't), and skipped entirely on restarts when nothing changed
- **Multi-Bot Mode**: host many bots on one server, each in its own folder with its own
  packages and `.env`, and control them from a web panel on the server's port
- **Upload or deploy from Git**: upload your files, or clone a Git repo (public or private)
  and optionally pull it on every start
- **Ready for Discord**: ffmpeg, Opus and libsodium are in the image for voice and music bots,
  plus a compiler for packages without a prebuilt wheel
- **Update check**: the console says when the egg or the Docker image has an update
- **Maintained images**: Debian based, `amd64` and `arm64`, rebuilt weekly for security fixes

## Requirements

- Pterodactyl Panel 1.x with Wings (the egg is in the `PTDL_v2` format)
- An `amd64` or `arm64` node
- Internet access from the node, for the Docker image, Python packages and your Git repo

## Install

1. Download [`egg-python.json`](https://github.com/Rustix-Development/pterodactyl-python-egg/releases/latest/download/egg-python.json)
   from the [latest release](https://github.com/Rustix-Development/pterodactyl-python-egg/releases/latest).
2. In the panel: **Admin → Nests → Import Egg**, upload it into the nest you want.
3. Create a server with the egg and pick a Python version under **Docker Image**.
   Set **Multi-Bot Mode** to `1` here if the server will host several bots.
4. Upload your bot (or set a Git repo) and start the server.

## Single app (default)

With Multi-Bot Mode off the server runs one Python app, like a plain Python egg:

1. Upload your files: the **Entry File** (`bot.py` by default) and a `requirements.txt`.
2. Start the server. The first start creates `.venv/` and installs your requirements; later
   starts skip that unless `requirements.txt`, *Extra Packages* or the Python version changed.

Need something other than `python bot.py`? Put it in **Custom Startup Command**, e.g.
`gunicorn app:app -b 0.0.0.0:$SERVER_PORT`. It runs inside the venv, so `pip` and any
installed tools are on the path.

## Multi-Bot Mode

Turn on **Multi-Bot Mode** when creating the server. Only an admin can change it later
(Admin → Servers → server → Startup), so a server's users can't switch it.

Each bot gets its own folder:

```
/home/container
├── welcomer/
│   ├── bot.py              # bot.py, main.py or app.py
│   ├── requirements.txt    # this bot's packages, in its own .venv
│   └── .env                # this bot's tokens and settings
├── radio/
│   ├── bot.py
│   ├── requirements.txt
│   ├── .env
│   └── .disabled           # optional: don't start this bot automatically
└── logs/                   # one log file per bot
```

- **Add a bot**: create a folder with a `bot.py` in it. The panel finds it within 10 seconds
  (or press *Rescan*), then start it.
- **Separate packages**: each bot has its own venv, so one bot can pin `discord.py==2.3.2`
  while another needs `discord.py>=2.6`. uv shares downloads between them, so this costs
  little disk space.
- **Separate secrets**: each bot only sees its own `.env`. The panel password and Git
  token are never passed to bots.
- **Crash recovery**: a bot that crashes is restarted after 5 seconds, then 10, 20, ... up to
  5 minutes between tries. A bot that exits cleanly (exit code 0) stays stopped.
- **Stopping**: bots get Ctrl+C first, so they can log out of Discord cleanly, and are
  only killed if they don't stop within 8 seconds. Stopping the server stops every bot.

### Web panel

Open `http://<node-ip>:<port>` (the server's primary allocation). From there you can:

- see each bot's state, uptime, CPU and memory, and the server's total memory use
- start, stop and restart a bot, or every bot at once
- watch a bot's live output
- turn auto-start on or off, or force a fresh dependency install

The password is the **Bot Panel Password** variable. If that's blank, one is generated and
shown in the console on every start (it's also in `.rustix/panel-password`). Logins are
limited to 10 wrong tries per 5 minutes. The panel speaks plain HTTP: put a reverse proxy or
Cloudflare in front of the port if you open it to the internet.

### Console commands

The server console also controls the bots. Type `help` for the list:

| Command | What it does |
|---------|--------------|
| `list` | Every bot with its state, CPU and memory |
| `start <bot>`, `stop <bot>`, `restart <bot>` | Use `all` for every bot |
| `enable <bot>`, `disable <bot>` | Turn auto-start on or off |
| `reinstall <bot>` | Force a fresh dependency install |
| `logs <bot> [lines]` | Print a bot's recent output |
| `rescan` | Look for new bot folders now |
| `password` | Show the web panel password |

## Variables

### Python

| Variable | Default | What it does |
|----------|---------|--------------|
| Multi-Bot Mode (`MULTI_BOT`) | `0` | Host several bots with a web panel. Admin only |
| Entry File (`PY_FILE`) | `bot.py` | File to run (single app) |
| Requirements File (`REQUIREMENTS_FILE`) | `requirements.txt` | Installed on start when it changes (single app) |
| Auto Install Dependencies (`AUTO_INSTALL`) | `1` | Install requirements and extra packages on start |
| Extra Packages (`PY_PACKAGES`) | | Space separated packages on top of the requirements file (single app) |
| Custom Startup Command (`CUSTOM_CMD`) | | Run this instead of the Entry File (single app) |
| Bot Panel Password (`PANEL_PASSWORD`) | | Web panel password; blank generates one |
| Bots Folder (`BOTS_DIR`) | | Folder holding the bot folders; blank is the server's main folder |
| Auto Restart Bots (`AUTO_RESTART`) | `1` | Restart crashed bots with backoff |
| Update Check (`UPDATE_CHECK`) | `1` | Say in the console when the egg or the Docker image has an update |

### Git

| Variable | Default | What it does |
|----------|---------|--------------|
| Git Repo Address (`GIT_ADDRESS`) | | Repo to clone on install, e.g. `https://github.com/you/your-bot` |
| Git Branch (`BRANCH`) | | Branch to clone; blank uses the repo's default branch |
| Auto Update (`AUTO_UPDATE`) | `0` | `git pull` on every start |
| User Uploaded Files (`USER_UPLOAD`) | `0` | Skip the Git setup, you upload the files yourself |
| Git Username (`USERNAME`) | | For private repos |
| Git Access Token (`ACCESS_TOKEN`) | | For private repos; use a personal access token, not your password |

The repo is only cloned into an empty server. If the server is already a clone of the same
repo, a reinstall pulls it; any other files are left alone. In Multi-Bot Mode the repo holds
the bot folders.

## What's in the image

The images are `ghcr.io/rustix-development/pterodactyl-python-egg:python3.11` up to `:python3.15`,
built from [`docker/Dockerfile`](docker/Dockerfile) on the official `python:*-slim` images with
uv, Git, ffmpeg, Opus, libsodium, build tools, tini and the bot manager
([`docker/rustix/`](docker/rustix)).

The start script and bot manager live in the image, not on the server, so restarting a server
picks up their updates without a reinstall.

## Files on your server

| Path | What it's for |
|------|---------------|
| `.venv/` | The app's packages (single app). Delete it to rebuild from scratch |
| `<bot>/.venv/` | Each bot's packages (Multi-Bot Mode) |
| `logs/` | One log per bot (Multi-Bot Mode). A log over 5 MB is moved to `*.log.1` |
| `.cache/` | uv and pip download cache, shared by every venv |
| `.rustix/` | Web panel session key and generated password |

## Moving from Python Universal (yajtpg)

1. Import this egg, then **Admin → Servers → server → Startup**: change the egg to this one,
   pick a **Docker Image**, and set the startup command to `rustix-start`.
2. If the old *Startup Command 2* was something other than `python bot.py`, set **Entry File**
   or **Custom Startup Command** to match.
3. For a server that ran the old `panel.py` with bot folders next to it, set **Multi-Bot
   Mode** to `1`. The folders, `.env` files and `.disabled` markers work as they are, and a
   `PANEL_PASSWORD` in the root `.env` is still used if the variable is blank. `panel.py` and
   the root `requirements.txt` aren't needed any more.

## Updates

Every time a server starts it checks for updates in the background and says in the console if:

- **the egg has an update**: download `egg-python.json` from the
  [latest release](https://github.com/Rustix-Development/pterodactyl-python-egg/releases/latest), then
  **Admin → Nests → (nest) → Python → Update Egg** with it (not *Import Egg*, that makes a
  second copy).
- **the Docker image has an update**: restart the server, the panel downloads the latest image
  on every start. If it keeps showing, run
  `docker pull ghcr.io/rustix-development/pterodactyl-python-egg:python3.x` on the node to see why.
- **the server's Python version is no longer offered**: **Admin → Servers → server → Startup →
  Docker Image**, pick one of the egg's images.

Turn it off per server with the *Update Check* variable.

## Building the images yourself

```sh
docker build --build-arg PYTHON_VERSION=3.13 -t pterodactyl-python-egg:python3.13 docker/
```

The [Build images](.github/workflows/build-images.yml) workflow builds every version for
`amd64` and `arm64` and pushes them to GHCR on every change to `docker/` and weekly.

## Troubleshooting

- **`Can't find bot.py`**: upload it, or set **Entry File** to your file's name.
- **A package fails to install**: the console shows the error. Brand-new Python versions
  (3.15) may not have prebuilt packages yet; pick an older Python under Docker Image.
- **A bot keeps restarting**: open its logs in the panel (or `logs <bot>` in the console);
  the error is just above `exited with code`.
- **Can't reach the web panel**: it listens on the server's primary allocation, and only in
  Multi-Bot Mode. The console says `Launching web panel on port ...` once it's up.
- **Git clone fails**: check the address, branch and, for a private repo, the username and
  access token. The clone only runs into an empty server.

Found a bug or want a feature? [Open an issue](https://github.com/Rustix-Development/pterodactyl-python-egg/issues).

## License

MIT, see [LICENSE](LICENSE). Git install logic from
[parkervcp/eggs](https://github.com/parkervcp/eggs); see [NOTICE.md](NOTICE.md) for credits
and their licenses.
