FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir .

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
CMD ["python", "-m", "smtpweb.web_main"]
