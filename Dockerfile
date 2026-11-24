FROM python:3.13-slim-trixie

RUN apt-get update \
    && apt-get install --yes --no-install-recommends ca-certificates git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml README.md ./
COPY detector/ ./detector/
COPY src/ ./src/
RUN python -m pip install --no-cache-dir '.[hosted]' \
    && git init -q /tmp/mergerisk-git-check \
    && python -c 'from pathlib import Path; from mergerisk.git.scenario import GitScenarioAssembler; print(GitScenarioAssembler(Path("/tmp/mergerisk-git-check")).git_version)' \
    && rm -rf /tmp/mergerisk-git-check

# Bundled libpq uses OpenSSL's default lookup for sslrootcert=system.
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8080 \
    SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt
USER 65532:65532
EXPOSE 8080
CMD ["python", "-m", "mergerisk.hosted"]
