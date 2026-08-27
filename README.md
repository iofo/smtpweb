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
```

## Running

```bash
python -m smtpweb.main
```

This starts:

- an SMTP server on `0.0.0.0:1025`
- a web UI on `http://0.0.0.0:8080`

Send it a test email:

```bash
python - <<'EOF'
import smtplib
from email.message import EmailMessage

msg = EmailMessage()
msg["From"] = "alice@example.com"
msg["To"] = "bob@example.com"
msg["Subject"] = "Hello"
msg.set_content("This is a test.")

with smtplib.SMTP("127.0.0.1", 1025) as s:
    s.send_message(msg)
EOF
```

Then open `http://127.0.0.1:8080` to see it in the inbox.

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
