FROM golang:1.23-bookworm@sha256:167053a2bb901972bf2c1611f8f52c44d5fe7e762e5cab213708d82c421614db

WORKDIR /app

RUN apt-get update -qq \
    && apt-get install -y -qq --no-install-recommends ca-certificates curl \
    && curl -LsSf https://astral.sh/uv/0.9.5/install.sh | sh \
    && rm -rf /var/lib/apt/lists/*

ENV PATH="/root/.local/bin:${PATH}"

RUN mkdir -p /sbwa/ro/out /app/bin

COPY slo-matrix/ /sbwa/ro/slo-matrix/

ENV SBWA_DATA_DIR=/sbwa/ro/slo-matrix
ENV SBWA_AUDIT_DIR=/sbwa/ro/out

ENV GOFLAGS="-mod=mod"
ENV GOTOOLCHAIN=local

CMD ["/bin/bash"]
