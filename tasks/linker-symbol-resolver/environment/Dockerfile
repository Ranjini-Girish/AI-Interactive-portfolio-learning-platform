FROM node:22-bookworm-slim@sha256:868499d55378719bffa87b0ed1f099591823c029b543043c09c2483468e93201

WORKDIR /app

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        asciinema \
        ca-certificates \
        python3 \
        python3-pip \
        tmux \
    && python3 -m pip install --no-cache-dir --break-system-packages \
        jsonschema==4.23.0 \
        pytest==8.4.1 \
        pytest-json-ctrf==0.3.5 \
    && rm -rf /var/lib/apt/lists/*

RUN ln -sf /usr/bin/python3 /usr/bin/python

COPY include/        /app/include/
COPY src/            /app/src/
COPY data/           /app/data/
COPY Makefile        /app/Makefile
COPY README.md       /app/README.md

RUN mkdir -p /app/output /app/build /app/src /app/oracle_pkg \
    && cd /app/oracle_pkg \
    && npm init -y \
    && npm install --save-exact typescript@5.7.3 tsx@4.19.3 @types/node@22.13.10 \
    && npm cache clean --force

CMD ["/bin/bash"]
