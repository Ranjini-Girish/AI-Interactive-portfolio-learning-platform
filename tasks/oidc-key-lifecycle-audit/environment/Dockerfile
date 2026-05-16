FROM python:3.13-slim-bookworm@sha256:f41a75c9cee9391c09e0139f7b49d4b1fbb119944ec740ecce4040626dc07bed

WORKDIR /app

COPY oidc_keys/ /app/oidc_keys/

RUN mkdir -p /app/audit

CMD ["/bin/bash"]
