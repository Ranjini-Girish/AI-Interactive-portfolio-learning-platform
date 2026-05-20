FROM debian:bookworm-slim@sha256:f9c6a2fd2ddbc23e336b6257a5245e31f996953ef06cd13a59fa0a1df2d5c252

ENV DEBIAN_FRONTEND=noninteractive

RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        g++ \
        make \
        nlohmann-json3-dev=3.11.2-1; \
    curl -LsSf https://astral.sh/uv/0.9.5/install.sh | sh; \
    /root/.local/bin/uv venv /opt/test-venv --python 3.13; \
    /root/.local/bin/uv pip install --python /opt/test-venv/bin/python \
        pytest==8.4.1 \
        pytest-json-ctrf==0.3.5; \
    rm -rf /root/.cache/uv /root/.local/share/uv; \
    apt-get purge -y curl; \
    apt-get autoremove -y; \
    apt-get clean; \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY Makefile /app/environment/Makefile
COPY include/ /app/include/
COPY src/ /app/src/
COPY data/ /app/data/
COPY docs/ /app/docs/
COPY schemas/ /app/schemas/
COPY examples/ /app/examples/

RUN make -C /app/environment build || true

ENV PATH="/opt/test-venv/bin:${PATH}"

CMD ["/bin/bash"]
