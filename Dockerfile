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


FROM base AS final

RUN useradd --create-home --uid 1000 smtpweb \
    && mkdir -p /data/mail /data/smtp/tls /data/web \
    && chown -R smtpweb:smtpweb /data
USER smtpweb

ENV SMTPWEB_MAIL_DIR=/data/mail \
    SMTPWEB_SMTP_STATE_DIR=/data/smtp \
    SMTPWEB_WEB_STATE_DIR=/data/web \
    SMTPWEB_SMTP_HOST=0.0.0.0 \
    SMTPWEB_SMTP_PORT=1025 \
    SMTPWEB_WEB_HOST=0.0.0.0 \
    SMTPWEB_WEB_PORT=8080

# Declared separately (not one shared /data) so docker-compose.yml can
# mount each into only the container/process that actually needs it —
# see README > Authentication for why that split matters.
VOLUME ["/data/mail", "/data/smtp", "/data/web"]
EXPOSE 1025 8080

# One image, two entrypoints — override the command to run either process
# (see docker-compose.yml, which runs both as separate services/containers).
CMD ["python", "-m", "smtpweb.web.main"]
