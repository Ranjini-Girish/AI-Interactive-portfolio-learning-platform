FROM python:3.13-slim-bookworm@sha256:f41a75c9cee9391c09e0139f7b49d4b1fbb119944ec740ecce4040626dc07bed

RUN python -m pip install --no-cache-dir \
    pytest==8.4.1 \
    pytest-json-ctrf==0.3.5

WORKDIR /app

COPY oauthlattice/ /app/oauthlattice/

RUN mkdir -p /app/audit

CMD ["/bin/bash"]
