FROM eclipse-temurin:21-jdk@sha256:be5aea962f8215d917d30c7d5a5ed32359580aef9c353b921487362b24650dde

WORKDIR /app

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        asciinema \
        ca-certificates \
        curl \
        python3 \
        python3-pip \
        sqlite3 \
        tmux \
    && curl -fsSL https://repo1.maven.org/maven2/com/google/code/gson/gson/2.11.0/gson-2.11.0.jar -o /opt/gson.jar \
    && echo "57928d6e5a6edeb2abd3770a8f95ba44dce45f3b23b7a9dc2b309c581552a78b  /opt/gson.jar" | sha256sum -c - \
    && curl -fsSL https://repo1.maven.org/maven2/org/xerial/sqlite-jdbc/3.46.1.3/sqlite-jdbc-3.46.1.3.jar -o /opt/sqlite-jdbc.jar \
    && echo "4a4832720a65eaf7f4d6fd7ede52087b994dc5633c076f9e994dc0c8b4b0b4fa  /opt/sqlite-jdbc.jar" | sha256sum -c - \
    && python3 -m pip install --no-cache-dir --break-system-packages \
        pytest==8.4.1 \
        pytest-json-ctrf==0.3.5 \
    && rm -rf /var/lib/apt/lists/*

RUN ln -sf /usr/bin/python3 /usr/bin/python

COPY requirements.txt /app/requirements.txt
COPY audit/ /app/audit/
COPY data/ /app/data/
COPY scripts/ /app/scripts/
COPY docs/ /app/docs/

RUN chmod +x /app/scripts/init_db.sh \
    && /app/scripts/init_db.sh \
    && mkdir -p /app/out

CMD ["/bin/bash"]
