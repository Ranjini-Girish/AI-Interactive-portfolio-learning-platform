FROM golang:1.24-bookworm@sha256:1a6d4452c65dea36aac2e2d606b01b4a029ec90cc1ae53890540ce6173ea77ac

WORKDIR /app

ENV GOCACHE=/tmp/.go-cache \
    GOPATH=/tmp/.go-path \
    GOMODCACHE=/tmp/.go-modcache \
    GOFLAGS="-mod=mod" \
    GOSUMDB=off \
    GONOSUMDB="*" \
    GONOPROXY="*" \
    PATH="/usr/local/go/bin:/go/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        python3 \
        python3-pip \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN python3 -m pip install --no-cache-dir --break-system-packages \
        pytest==8.4.1 \
        pytest-json-ctrf==0.3.5

RUN mkdir -p /app/audit /app/build /app/src

COPY stream/ /app/stream/

CMD ["/bin/bash"]
