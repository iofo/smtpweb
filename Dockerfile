FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY pyproject.toml ./
COPY src ./src
# `pip install .` leaves its own build byproducts (build/lib/, a
# duplicate copy of the whole package; src/*.egg-info) sitting in the
# working directory — harmless (no secrets, just the app's own public
# source again) but pointless bloat in a shipped image.
RUN pip install --no-cache-dir . && rm -rf build src/*.egg-info


# `docker build --target test -t smtpweb:test . && docker run --rm smtpweb:test`
# Runs pytest against the actual packaged install (catches issues an
# editable dev install wouldn't, e.g. missing package-data). Not part of
# the default build target, so it never ships in the production image.
FROM base AS test

COPY requirements-test.txt ./
RUN pip install --no-cache-dir -r requirements-test.txt
COPY tests ./tests
CMD ["pytest"]


# `docker build --target lint -t smtpweb:lint . && docker run --rm smtpweb:lint`
# Same rationale as the test stage: lints/formats-checks the actual
# packaged source, not part of the default build target.
FROM base AS lint

COPY requirements-lint.txt ./
RUN pip install --no-cache-dir -r requirements-lint.txt
COPY tests ./tests
CMD ["sh", "-c", "ruff check . && ruff format --check ."]


FROM base AS final

# gosu: lets the entrypoint start as root just long enough to fix up
# bind-mount ownership (see entrypoint.sh), then drop to smtpweb -- unlike
# `su`, it execs directly with no shell/subprocess in between, so signals
# still reach the app process correctly.
RUN apt-get update \
    && apt-get install -y --no-install-recommends gosu \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 1000 smtpweb \
    && mkdir -p /data/mail /data/smtp/tls /data/web \
    && chown -R smtpweb:smtpweb /data

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Set by CI (see .github/workflows/docker.yml's publish job) to the
# commit it's building from, so the running web UI can show it -- "dev"
# for a plain local `docker build` with no --build-arg passed.
ARG GIT_SHA=dev

ENV SMTPWEB_MAIL_DIR=/data/mail \
    SMTPWEB_SMTP_STATE_DIR=/data/smtp \
    SMTPWEB_WEB_STATE_DIR=/data/web \
    SMTPWEB_SMTP_HOST=0.0.0.0 \
    SMTPWEB_SMTP_PORT=1025 \
    SMTPWEB_WEB_HOST=0.0.0.0 \
    SMTPWEB_WEB_PORT=8080 \
    SMTPWEB_GIT_SHA=$GIT_SHA

# Declared separately (not one shared /data) so docker-compose.yml can
# mount each into only the container/process that actually needs it —
# see README > Authentication for why that split matters.
VOLUME ["/data/mail", "/data/smtp", "/data/web"]
EXPOSE 1025 8080

ENTRYPOINT ["/entrypoint.sh"]

# One image, two entrypoints — override the command to run either process
# (see docker-compose.yml, which runs both as separate services/containers).
CMD ["python", "-m", "smtpweb.web.main"]
