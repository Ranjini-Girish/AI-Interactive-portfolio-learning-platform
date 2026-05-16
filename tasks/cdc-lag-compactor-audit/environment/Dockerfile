FROM rust:1.83-slim-bookworm@sha256:540c902e99c384163b688bbd8b5b8520e94e7731b27f7bd0eaa56ae1960627ab

WORKDIR /app
ENV PATH="/usr/local/cargo/bin:${PATH}"

COPY cdc/ /app/cdc/
COPY auditor/ /app/auditor/

RUN mkdir -p /app/audit /app/bin

CMD ["/bin/bash"]
