FROM node:22-bookworm-slim@sha256:868499d55378719bffa87b0ed1f099591823c029b543043c09c2483468e93201

WORKDIR /app

COPY flags/ /app/flags/
COPY rollout_package.json /app/rollout/package.json
COPY rollout_tsconfig.json /app/rollout/tsconfig.json
COPY rollout_src_main.ts /app/rollout/src/main.ts

RUN mkdir -p /app/audit \
 && cd /app/rollout \
 && npm install \
 && npm cache clean --force

CMD ["/bin/bash"]
