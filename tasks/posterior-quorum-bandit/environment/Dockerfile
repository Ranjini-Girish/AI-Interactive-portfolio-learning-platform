FROM rust:1.85-bookworm@sha256:e51d0265072d2d9d5d320f6a44dde6b9ef13653b035098febd68cce8fa7c0bc4

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        asciinema \
        ca-certificates \
        python3 \
        python3-pip \
        tmux \
    && ln -sf /usr/bin/python3 /usr/bin/python \
    && rm -rf /var/lib/apt/lists/*

RUN python3 -m pip install --no-cache-dir --break-system-packages \
    pytest==8.4.1 \
    pytest-json-ctrf==0.3.5

RUN mkdir -p /opt/bootstrap/src \
    && printf '%s\n' \
    '[package]' \
    'name = "bootstrap"' \
    'version = "0.0.0"' \
    'edition = "2021"' \
    '' \
    '[dependencies]' \
    'serde = { version = "1.0.210", features = ["derive"] }' \
    'serde_json = "1.0.128"' \
    'sha2 = "0.10.8"' \
    > /opt/bootstrap/Cargo.toml \
    && printf 'fn main() {}\n' > /opt/bootstrap/src/main.rs \
    && cd /opt/bootstrap && cargo fetch \
    && rm -rf /opt/bootstrap

ENV CARGO_NET_OFFLINE=true

COPY pqb_lab/ /app/pqb_lab/
COPY pqb_auditor/ /app/pqb_auditor/

RUN cd /app/pqb_auditor && cargo fetch && cargo build --release --quiet

RUN mkdir -p /app/audit /app/bin

CMD ["/bin/bash"]
