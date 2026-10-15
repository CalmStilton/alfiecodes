# code-server + Python tooling for Alfie. Runs as the image's non-root user (abc).
FROM lscr.io/linuxserver/code-server:latest

RUN apt-get update \
 && apt-get install -y --no-install-recommends python3 python3-pip python3-venv \
 && rm -rf /var/lib/apt/lists/* \
 && pip install --no-cache-dir --break-system-packages pygame-ce pygbag numpy \
 && pip install --no-cache-dir --break-system-packages --no-deps pgzero

LABEL org.opencontainers.image.source="https://github.com/CalmStilton/alfiecodes"
