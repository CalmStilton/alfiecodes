# code-server + Python tooling for Alfie. Runs as the image's non-root user (abc).
FROM lscr.io/linuxserver/code-server:latest

RUN apt-get update \
 && apt-get install -y --no-install-recommends python3 python3-pip python3-venv \
 && rm -rf /var/lib/apt/lists/* \
 && pip install --no-cache-dir --break-system-packages pygame-ce pygbag numpy \
 && pip install --no-cache-dir --break-system-packages --no-deps pgzero

# pgzlite + the publish tool. `publish` builds a project for the browser and adds it to /published.
COPY pgzlite.py publish.py autosave.sh /opt/alfiecodes/
RUN chmod 0755 /opt/alfiecodes/publish.py /opt/alfiecodes/autosave.sh \
 && ln -s /opt/alfiecodes/publish.py /usr/local/bin/publish \
 && ln -s /opt/alfiecodes/autosave.sh /usr/local/bin/autosave \
 && mkdir -p /published && chown 1000:1000 /published

LABEL org.opencontainers.image.source="https://github.com/CalmStilton/alfiecodes"
