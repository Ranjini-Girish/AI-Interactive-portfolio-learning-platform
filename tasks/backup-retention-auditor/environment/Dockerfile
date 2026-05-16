FROM ghcr.io/astral-sh/uv:0.9.5@sha256:f459f6f73a8c4ef5d69f4e6fbbdb8af751d6fa40ec34b39a1ab469acd6e289b7 AS uvbin

FROM rust:1.83-slim-bookworm@sha256:540c902e99c384163b688bbd8b5b8520e94e7731b27f7bd0eaa56ae1960627ab

COPY --from=uvbin /uv /uvx /usr/local/bin/

WORKDIR /app

COPY data/ /app/data/
COPY auditor/ /app/auditor/

RUN mkdir -p /app/audit \
 && cd /app/auditor \
 && cargo fetch --locked

CMD ["/bin/bash"]
