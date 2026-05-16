FROM rust:1.83-slim-bookworm@sha256:540c902e99c384163b688bbd8b5b8520e94e7731b27f7bd0eaa56ae1960627ab

WORKDIR /app

RUN set -eux \
 && mkdir -p /opt/_prefetch/src \
 && printf '[package]\nname = "prefetch"\nversion = "0.0.1"\nedition = "2021"\n\n[dependencies]\nserde = { version = "1", features = ["derive"] }\nserde_json = "1"\n' > /opt/_prefetch/Cargo.toml \
 && echo 'fn main() {}' > /opt/_prefetch/src/main.rs \
 && cargo fetch --manifest-path /opt/_prefetch/Cargo.toml \
 && rm -rf /opt/_prefetch

COPY workspace/ /app/workspace/

RUN mkdir -p /app/plan /app/planner
RUN set -eux \
 && cargo init --bin --name planner /app/planner --vcs none \
 && printf '\nserde = { version = "1", features = ["derive"] }\nserde_json = "1"\n' >> /app/planner/Cargo.toml

CMD ["/bin/bash"]
