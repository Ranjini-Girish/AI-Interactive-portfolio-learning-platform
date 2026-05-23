FROM python:3.13-slim-bookworm@sha256:8bc60ca09afaa8ea0d6d1220bde073bacfedd66a4bf8129cbdc8ef0e16c8a952

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        asciinema \
        ca-certificates \
        tmux \
    && rm -rf /var/lib/apt/lists/*

RUN python -m pip install --no-cache-dir \
    pytest==8.4.1 \
    pytest-json-ctrf==0.3.5 \
    PyYAML==6.0.1

COPY data/ /app/data/
COPY docs/ /app/docs/
COPY schemas/ /app/schemas/

RUN mkdir -p /app/output

CMD ["/bin/bash"]
