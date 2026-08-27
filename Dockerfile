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
    && mkdir -p /data/emails \
    && chown -R smtpweb:smtpweb /data
USER smtpweb

ENV SMTPWEB_DATA_DIR=/data/emails \
    SMTPWEB_SMTP_HOST=0.0.0.0 \
    SMTPWEB_SMTP_PORT=1025 \
    SMTPWEB_WEB_HOST=0.0.0.0 \
    SMTPWEB_WEB_PORT=8080

VOLUME ["/data"]
EXPOSE 1025 8080

CMD ["python", "-m", "smtpweb.main"]
