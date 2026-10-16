#!/bin/bash
# rustix-start: the egg's startup command.
#   MULTI_BOT=1 -> Rustix bot manager + web panel (each bot in its own folder)
#   MULTI_BOT=0 -> plain Python: one venv, one entry file (or a custom command)
cd /home/container || exit 1

EGG_REPO="Rustix-Development/pterodactyl-python-egg"
EGG_IMAGE="rustix-development/pterodactyl-python-egg"
EGG_FILE="egg-python.json"
R=/opt/rustix
RPY=$R/venv/bin/python
PYV=${RUSTIX_PYTHON_VERSION}

GREEN="\033[0;32m"
YELLOW="\033[1;33m"
RED="\033[0;31m"
CYAN="\033[1;36m"
ORANGE="\033[38;5;208m"
RESET="\033[0m"

log_info()    { printf "${ORANGE}[rustix]${RESET} %s\n" "$1"; }
log_success() { printf "${GREEN}[SUCCESS] %s${RESET}\n" "$1"; }
log_warning() { printf "${YELLOW}[WARNING] %s${RESET}\n" "$1"; }
log_error()   { printf "${RED}[ERROR] %s${RESET}\n" "$1"; }
log_update()  { printf "${CYAN}[UPDATE] %s${RESET}\n" "$1"; }

is_true() { case "${1,,}" in 1|true|yes|on) return 0 ;; *) return 1 ;; esac; }

# Compare the EGG_VERSION this server was installed with against the latest released egg
check_egg_update() {
    if ! egg_json=$(curl -fsL --max-time 10 "https://github.com/${EGG_REPO}/releases/latest/download/${EGG_FILE}"); then
        log_warning "Update check: couldn't get the latest egg from GitHub, skipping."
        return
    fi
    latest=$(printf '%s' "${egg_json}" | grep -o 'EGG_VERSION=\\"[^\\]*' | head -n 1 | sed 's/.*\\"//')
    installed=$(cat /home/container/.egg-version 2>/dev/null)
    [ -z "${latest}" ] && return

    if [ "${installed}" = "${latest}" ]; then
        log_success "Egg is up to date (v${installed})."
    else
        log_update "Egg update available: ${installed:+v${installed} -> }v${latest}"
        log_update "  1. Download ${EGG_FILE} from https://github.com/${EGG_REPO}/releases/latest"
        log_update "     and upload it in the panel: Admin -> Nests -> (nest) -> Python -> Update Egg"
        log_update "  2. This server: Settings -> Reinstall Server. Your files are kept."
    fi

    if [ -n "${PYV}" ] && ! printf '%s' "${egg_json}" | grep -q "pterodactyl-python-egg:python${PYV}\""; then
        log_warning "Python ${PYV} is no longer offered by the egg. Admin -> Servers -> this server -> Startup -> Docker Image: pick one of the egg's images."
    fi
}

# Compare this Docker image's build time against the latest build on ghcr.io
check_image_update() {
    if [ -z "${IMAGE_BUILD}" ] || [ -z "${PYV}" ]; then
        log_warning "This server isn't using a Rustix Python Docker image. Admin -> Servers -> this server -> Startup -> Docker Image: pick one of the egg's images."
        return
    fi
    [ "${IMAGE_BUILD}" = "dev" ] && return

    token=$(curl -fs --max-time 10 "https://ghcr.io/token?scope=repository:${EGG_IMAGE}:pull" \
        | sed -n 's/.*"token"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')
    if ! index=$(curl -fs --max-time 10 -H "Authorization: Bearer ${token}" \
        -H "Accept: application/vnd.oci.image.index.v1+json, application/vnd.docker.distribution.manifest.list.v2+json, application/vnd.oci.image.manifest.v1+json" \
        "https://ghcr.io/v2/${EGG_IMAGE}/manifests/python${PYV}"); then
        log_warning "Update check: couldn't get the latest Docker image info from ghcr.io, skipping."
        return
    fi
    latest=$(printf '%s' "${index}" | grep -o '"org.opencontainers.image.created"[[:space:]]*:[[:space:]]*"[^"]*"' \
        | head -n 1 | sed 's/.*"\([^"]*\)"$/\1/')
    [ -z "${latest}" ] && return

    # ISO 8601 timestamps sort as text
    newest=$(printf '%s\n%s\n' "${latest}" "${IMAGE_BUILD}" | sort | tail -n 1)
    if [ "${newest}" = "${IMAGE_BUILD}" ]; then
        log_success "Docker image is up to date (Python ${PYV}, built ${IMAGE_BUILD%%T*})."
    else
        log_update "Docker image update available: built ${latest%%T*}, this server runs ${IMAGE_BUILD%%T*}."
        log_update "  Restart the server to download it (the panel pulls the latest image on every start)."
        log_update "  If this keeps showing, run 'docker pull ghcr.io/${EGG_IMAGE}:python${PYV}' on the node to see why."
    fi

    # The weekly rebuild stops if GitHub disables the scheduled workflow (60 days without repo activity)
    latest_ts=$(date -u -d "${latest}" +%s 2>/dev/null)
    now_ts=$(date -u +%s)
    if [ -n "${latest_ts}" ] && [ $(( (now_ts - latest_ts) / 86400 )) -gt 21 ]; then
        log_warning "The egg's Docker images haven't been rebuilt for $(( (now_ts - latest_ts) / 86400 )) days, so they may be missing security updates. See https://github.com/${EGG_REPO}"
    fi
}

export UV_CACHE_DIR=${UV_CACHE_DIR:-/home/container/.cache/uv}
export PIP_CACHE_DIR=${PIP_CACHE_DIR:-/home/container/.cache/pip}
# Never wait for a git username/password on the console, just fail
export GIT_TERMINAL_PROMPT=0
mkdir -p logs .cache

if is_true "${UPDATE_CHECK:-1}" && command -v curl >/dev/null 2>&1; then
    # Double fork: never delays startup, ends with the container
    ( (check_egg_update; check_image_update) & )
fi

# ---- Git ----------------------------------------------------------------------
if is_true "${AUTO_UPDATE:-0}"; then
    if [ -d .git ]; then
        log_info "Auto Update: pulling latest files..."
        if git -c safe.directory=/home/container pull --ff-only; then
            log_success "Files updated."
        else
            log_warning "git pull failed, starting with the files already on the server."
        fi
    else
        log_warning "Auto Update is on but this server is not a git repository, skipping."
    fi
fi

# ---- Multi-bot mode -----------------------------------------------------------
if is_true "${MULTI_BOT:-0}"; then
    log_info "Multi-bot mode: starting the bot manager"
    exec "$RPY" -u "$R/manager.py"
fi

# ---- Single app ---------------------------------------------------------------
VENV=/home/container/.venv
if is_true "${AUTO_INSTALL:-1}"; then
    "$RPY" "$R/deps.py" --dir /home/container --venv "$VENV" \
        --req "${REQUIREMENTS_FILE:-requirements.txt}" --extra "${PY_PACKAGES}" \
        || log_warning "Dependency install failed, trying to start anyway."
elif [ ! -x "$VENV/bin/python" ]; then
    "$RPY" "$R/deps.py" --dir /home/container --venv "$VENV" --req "" --extra ""
fi

export VIRTUAL_ENV=$VENV PATH="$VENV/bin:$PATH"

if [ -n "${CUSTOM_CMD}" ]; then
    log_info "Launching custom command: ${CUSTOM_CMD}"
    exec bash -c "${CUSTOM_CMD}"
fi

PY_FILE=${PY_FILE:-bot.py}
if [ ! -f "$PY_FILE" ]; then
    log_error "Can't find ${PY_FILE}. Upload it, or change the Entry File variable in the Startup tab."
    exit 1
fi
log_info "Launching ${PY_FILE}"
exec python -u "$PY_FILE"
