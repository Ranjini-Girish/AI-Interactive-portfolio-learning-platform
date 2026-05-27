FROM debian:bookworm-slim@sha256:f9c6a2fd2ddbc23e336b6257a5245e31f996953ef06cd13a59fa0a1df2d5c252

ENV DEBIAN_FRONTEND=noninteractive

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        tmux \
        asciinema \
        openjdk-17-jdk \
        wget \
        ca-certificates \
        python3 \
        python3-pip \
        python-is-python3 \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /usr/share/java \
    && wget -q https://repo1.maven.org/maven2/com/google/code/gson/gson/2.11.0/gson-2.11.0.jar -O /usr/share/java/gson.jar \
    && python3 -m pip install --no-cache-dir --break-system-packages \
        pytest==8.4.1 \
        pytest-json-ctrf==0.3.5

COPY quota_lab/ /app/quota_lab/

RUN mkdir -p /app/audit

CMD ["/bin/bash"]
