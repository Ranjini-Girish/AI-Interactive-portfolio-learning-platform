FROM node:22-bookworm-slim@sha256:868499d55378719bffa87b0ed1f099591823c029b543043c09c2483468e93201

WORKDIR /app

COPY runs/ /app/runs/

COPY planner_package.json /app/planner/package.json
COPY planner_tsconfig.json /app/planner/tsconfig.json
COPY planner_src_main.ts /app/planner/src/main.ts

RUN mkdir -p /app/plan \
 && cd /app/planner \
 && npm install \
 && npm cache clean --force

CMD ["/bin/bash"]
