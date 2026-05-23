FROM rust:1.85-bookworm@sha256:e51d0265072d2d9d5d320f6a44dde6b9ef13653b035098febd68cce8fa7c0bc4

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

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
    > /opt/bootstrap/Cargo.toml \
    && printf 'fn main() {}\n' > /opt/bootstrap/src/main.rs \
    && cd /opt/bootstrap && cargo fetch \
    && rm -rf /opt/bootstrap

COPY data/ /app/data/

RUN mkdir -p /app/output

CMD ["/bin/bash"]
