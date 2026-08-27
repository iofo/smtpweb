# smtpweb

An SMTP server that accepts incoming email and writes each message to the
filesystem, plus a web UI to browse received emails and download
attachments.

- SMTP handling: [`aiosmtpd`](https://aiosmtpd.readthedocs.io/)
- Web backend: [FastAPI](https://fastapi.tiangolo.com/) + [Uvicorn](https://www.uvicorn.org/)
- Frontend: static HTML/CSS/vanilla JS served by FastAPI

## Setup

Requires Python 3.10+.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
# or: pip install -r requirements.txt
```

## Running

```bash
python -m smtpweb.main
```

This starts:

- an SMTP server on `0.0.0.0:1025`
- a web UI on `http://0.0.0.0:8080`

Send it some test emails:

```bash
python scripts/send_test_emails.py
```

Then open `http://127.0.0.1:8080` to see them in the inbox.

## Configuration

All settings are read from environment variables:

| Variable              | Default          | Description                       |
|-----------------------|------------------|------------------------------------|
| `SMTPWEB_SMTP_HOST`   | `0.0.0.0`        | SMTP listen address                |
| `SMTPWEB_SMTP_PORT`   | `1025`           | SMTP listen port                   |
| `SMTPWEB_WEB_HOST`    | `0.0.0.0`        | Web UI listen address              |
| `SMTPWEB_WEB_PORT`    | `8080`           | Web UI listen port                 |
| `SMTPWEB_DATA_DIR`    | `./data/emails`  | Directory emails are stored under  |

Binding to the standard SMTP port 25 requires root privileges; the default
port 1025 avoids that for local development.

## Docker

```bash
docker build -t smtpweb .
docker run -d --name smtpweb \
  -p 1025:1025 -p 8080:8080 \
  -v smtpweb-data:/data \
  smtpweb
```

Emails are stored at `/data/emails` inside the container (`SMTPWEB_DATA_DIR`);
mount a volume there to persist them across container restarts.

Or with Docker Compose:

```bash
docker compose up -d --build
```

## Storage layout

Each received email is stored in its own directory under `SMTPWEB_DATA_DIR`:

```
<data_dir>/<email-id>/
  raw.eml              # the full original message
  metadata.json         # parsed headers, recipients, attachment index
  body.txt               # text/plain part, if present
  body.html              # text/html part, if present
  attachments/<filename>
```

## API

- `GET /api/emails` — list received emails (metadata only)
- `GET /api/emails/{id}` — full detail, including body text/html
- `GET /api/emails/{id}/raw` — download the original `.eml`
- `GET /api/emails/{id}/attachments/{filename}` — download an attachment
