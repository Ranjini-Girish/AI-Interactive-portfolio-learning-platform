# Base image MUST be pinned to a content digest. Resolve once with:
#   docker pull python:3.13-slim-bookworm
#   docker inspect python:3.13-slim-bookworm --format='{{index .RepoDigests 0}}'
# then replace the @sha256:... below with the actual value.
FROM python:3.13-slim-bookworm@sha256:REPLACE_WITH_REAL_DIGEST

# Verifier deps must be pre-installed in the image — `allow_internet = false`
# means tests/test.sh CANNOT apt-get / pip-install / curl at runtime.
# Add task-specific Python deps to the pip block below; add system packages
# the agent's runtime actually needs to the apt block above.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        tmux \
        asciinema \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN python -m pip install --no-cache-dir \
    pytest==8.4.1 \
    pytest-json-ctrf==0.3.5

WORKDIR /app
