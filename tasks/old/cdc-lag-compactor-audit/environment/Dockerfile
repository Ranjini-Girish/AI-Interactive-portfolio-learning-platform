FROM rust:1.83-slim-bookworm@sha256:540c902e99c384163b688bbd8b5b8520e94e7731b27f7bd0eaa56ae1960627ab

WORKDIR /app
ENV PATH="/usr/local/cargo/bin:${PATH}"

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        asciinema \
        ca-certificates \
        python3 \
        python3-pip \
        tmux \
    && rm -rf /var/lib/apt/lists/*

RUN python3 -m pip install --no-cache-dir --break-system-packages \
        pytest==8.4.1 \
        pytest-json-ctrf==0.3.5

RUN ln -sf /usr/bin/python3 /usr/bin/python

COPY cdc/ /app/cdc/
COPY auditor/ /app/auditor/

RUN mkdir -p /app/audit /app/bin

CMD ["/bin/bash"]
