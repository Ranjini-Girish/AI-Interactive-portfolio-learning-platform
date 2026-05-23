FROM debian:bookworm-slim@sha256:f9c6a2fd2ddbc23e336b6257a5245e31f996953ef06cd13a59fa0a1df2d5c252

ENV DEBIAN_FRONTEND=noninteractive

RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        binutils \
        ca-certificates \
        g++ \
        make \
        nlohmann-json3-dev; \
    apt-get clean; \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY data/      /app/data/
COPY docs/      /app/docs/
COPY schemas/   /app/schemas/
COPY examples/  /app/examples/

CMD ["/bin/bash"]
