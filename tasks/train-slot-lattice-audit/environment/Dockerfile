FROM golang:1.23-bookworm@sha256:167053a2bb901972bf2c1611f8f52c44d5fe7e762e5cab213708d82c421614db

WORKDIR /app

COPY tslattice/ /app/tslattice/

RUN mkdir -p /app/audit

ENV GOFLAGS="-mod=mod"
ENV GOTOOLCHAIN=local

RUN apt-get update \
  && apt-get install -y --no-install-recommends ca-certificates curl \
  && curl -LsSf https://astral.sh/uv/0.9.5/install.sh | sh \
  && /root/.local/bin/uv venv /opt/test-venv --python 3.13 \
  && /root/.local/bin/uv pip install --python /opt/test-venv/bin/python \
    pytest==8.4.1 \
    pytest-json-ctrf==0.3.5 \
  && rm -rf /root/.cache/uv /root/.local/share/uv \
  && apt-get purge -y curl \
  && apt-get autoremove -y \
  && rm -rf /var/lib/apt/lists/*

ENV PATH="/opt/test-venv/bin:${PATH}"

CMD ["/bin/bash"]
