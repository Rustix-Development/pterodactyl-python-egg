# Runtime image for the Rustix Python egg: Python + uv + the Rustix bot manager.
# Build with: docker build --build-arg PYTHON_VERSION=3.13 docker/
ARG PYTHON_VERSION=3.13
FROM python:${PYTHON_VERSION}-slim

ARG PYTHON_VERSION
ARG UV_VERSION=0.13.1

LABEL org.opencontainers.image.source="https://github.com/Rustix-Development/pterodactyl-python-egg" \
      org.opencontainers.image.description="Python runtime for the Rustix Python Pterodactyl egg (single app or multi-bot with web panel)" \
      org.opencontainers.image.vendor="Rustix" \
      org.opencontainers.image.licenses="MIT"

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_INPUT=1 \
    UV_LINK_MODE=hardlink \
    UV_PYTHON_DOWNLOADS=never \
    RUSTIX_PYTHON_VERSION=${PYTHON_VERSION}

# Runtime libs Discord/voice/media bots usually need, plus a compiler for
# packages that ship no wheel for brand-new Python versions.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      tini git curl ca-certificates tzdata iproute2 procps \
      ffmpeg libopus0 libsodium23 libffi-dev libssl-dev \
      build-essential pkg-config \
 && rm -rf /var/lib/apt/lists/* \
 && useradd -m -d /home/container -s /bin/bash container

# Manager runtime lives in its own venv so it never collides with bot packages.
COPY rustix/requirements.txt /opt/rustix/requirements.txt
RUN python -m venv /opt/rustix/venv \
 && /opt/rustix/venv/bin/pip install --no-cache-dir -r /opt/rustix/requirements.txt "uv==${UV_VERSION}" \
 && ln -s /opt/rustix/venv/bin/uv /usr/local/bin/uv

COPY rustix/ /opt/rustix/
COPY entrypoint.sh /entrypoint.sh
RUN chmod 755 /entrypoint.sh /opt/rustix/start.sh \
 && ln -s /opt/rustix/start.sh /usr/local/bin/rustix-start \
 && ln -s /opt/rustix/start.sh /start.sh \
 && python -m compileall -q /opt/rustix

USER container
ENV USER=container HOME=/home/container
WORKDIR /home/container

# Used by the update check; the workflow passes the build time (also set as an index
# annotation) and the image's name
ARG IMAGE_BUILD=dev
ARG IMAGE_NAME=""
ENV IMAGE_BUILD=${IMAGE_BUILD} IMAGE_NAME=${IMAGE_NAME}

STOPSIGNAL SIGINT
ENTRYPOINT ["/usr/bin/tini", "-g", "--"]
CMD ["/entrypoint.sh"]
