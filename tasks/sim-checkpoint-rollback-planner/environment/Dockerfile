FROM node:22-bookworm-slim@sha256:868499d55378719bffa87b0ed1f099591823c029b543043c09c2483468e93201

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        python3 \
        python3-pip \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN python3 -m pip install --no-cache-dir --break-system-packages \
        pytest==8.4.1 \
        pytest-json-ctrf==0.3.5

COPY runs/ /app/runs/

COPY planner_package.json /app/planner/package.json
COPY planner_tsconfig.json /app/planner/tsconfig.json
COPY planner_src_main.ts /app/planner/src/main.ts

RUN mkdir -p /app/plan \
    && cd /app/planner \
    && npm install \
    && npm cache clean --force

CMD ["/bin/bash"]
