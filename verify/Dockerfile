FROM node:20-bookworm-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        python3 python3-venv python3-pip ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /work
COPY . .

# Pre-install everything at image-build time so the one-shot run needs no
# network access: backend test deps and frontend node modules.
RUN python3 -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir -r api/requirements-test.txt
RUN cd web && npm ci

CMD ["bash", "verify/run_verify.sh"]
