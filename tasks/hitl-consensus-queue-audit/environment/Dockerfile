FROM rust:1.83-slim-bookworm@sha256:540c902e99c384163b688bbd8b5b8520e94e7731b27f7bd0eaa56ae1960627ab

WORKDIR /app

COPY hitl/ /app/hitl/
COPY auditor/ /app/auditor/

RUN mkdir -p /app/audit /app/bin \
 && cd /app/auditor \
 && cargo fetch \
 && cargo build --quiet

CMD ["/bin/bash"]
