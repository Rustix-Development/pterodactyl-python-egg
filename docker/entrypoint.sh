#!/bin/bash
# Pterodactyl entrypoint: expand {{VARIABLES}} in the panel's startup command and run it.

cd /home/container || exit 1

INTERNAL_IP=$(ip route get 1 2>/dev/null | awk '{print $(NF-2); exit}')
export INTERNAL_IP
export TZ=${TZ:-UTC}

printf "\033[38;5;208m[rustix]\033[0m Python %s (%s)\n" "$(python -c 'import platform; print(platform.python_version())')" "$(uname -m)"

# shellcheck disable=SC2016
STARTUP=${STARTUP:-rustix-start}
MODIFIED_STARTUP=$(echo -e "${STARTUP}" | sed -e 's/{{/${/g' -e 's/}}/}/g')

if [ -z "${MODIFIED_STARTUP// }" ]; then
    printf "\033[0;31m[ERROR] The startup command is empty. Set it in the Startup tab (default: rustix-start).\033[0m\n"
    exit 1
fi

printf "\033[1m\033[33mcontainer@pterodactyl~ \033[0m%s\n" "$(eval echo "${MODIFIED_STARTUP}")"

# shellcheck disable=SC2086
eval exec ${MODIFIED_STARTUP}
