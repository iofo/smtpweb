# smtpweb

An SMTP server that accepts incoming email and writes each message to the
filesystem, plus a web UI to browse received emails and download
attachments.

- SMTP handling: [`aiosmtpd`](https://aiosmtpd.readthedocs.io/)
- Web backend: [FastAPI](https://fastapi.tiangolo.com/) + [Uvicorn](https://www.uvicorn.org/)
- Frontend: static HTML/CSS/vanilla JS served by FastAPI

## Architecture

SMTP receipt and the web UI are two independent processes/services —
`smtpweb.smtp_main` and `smtpweb.web_main` — that share nothing but the
data directory on disk. There's no in-memory state or IPC between them:
the SMTP process writes each message straight to `SMTPWEB_DATA_DIR`, and
the web process reads that same directory on every API request. Each has
its own separate authentication (see below), so a compromise of one
doesn't hand over the other's credentials, and in Docker they run as two
separate containers so you can expose SMTP publicly while keeping the web
UI off the public network.

## Setup

Requires Python 3.10+.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
# or: pip install -r requirements.txt
```

## Running

Run each process (in separate terminals):

```bash
python -m smtpweb.smtp_main
python -m smtpweb.web_main
```

This starts:

- an SMTP server on `0.0.0.0:1025`
- a web UI on `http://0.0.0.0:8080`

On first run, since no credentials are configured, each process generates
its own random username/password and prints where they were saved — see
[Authentication](#authentication) below. Send some test emails (the
script authenticates automatically using the generated SMTP credentials):

```bash
python scripts/send_test_emails.py
```

Then open `http://127.0.0.1:8080` and log in with the generated web
credentials (from `data/web_credentials.json`) to see them in the inbox.

## Configuration

All settings are read from environment variables:

| Variable                 | Default          | Description                        |
|---------------------------|------------------|-------------------------------------|
| `SMTPWEB_SMTP_HOST`      | `0.0.0.0`        | SMTP listen address                |
| `SMTPWEB_SMTP_PORT`      | `1025`           | SMTP listen port                   |
| `SMTPWEB_SMTP_USERNAME`  | *(generated)*    | SMTP AUTH username                 |
| `SMTPWEB_SMTP_PASSWORD`  | *(generated)*    | SMTP AUTH password                 |
| `SMTPWEB_WEB_HOST`       | `0.0.0.0`        | Web UI listen address              |
| `SMTPWEB_WEB_PORT`       | `8080`           | Web UI listen port                 |
| `SMTPWEB_WEB_USERNAME`   | *(generated)*    | Web UI Basic Auth username         |
| `SMTPWEB_WEB_PASSWORD`   | *(generated)*    | Web UI Basic Auth password         |
| `SMTPWEB_DATA_DIR`       | `./data/emails`  | Directory emails are stored under  |

Binding to the standard SMTP port 25 requires root privileges; the default
port 1025 avoids that for local development.

## Authentication

Both processes require auth, and neither has an open/anonymous mode:

**SMTP** always requires `AUTH`, over `STARTTLS` only. On startup it
presents a self-signed TLS certificate, auto-generated on first run and
cached at `<data_dir>/../tls/` (reused on restart). Set both
`SMTPWEB_SMTP_USERNAME` and `SMTPWEB_SMTP_PASSWORD` to use your own
credentials, or leave both unset and the server generates a random
password on first run, writing it to `<data_dir>/../smtp_credentials.json`
(reused on restart). Since the certificate is self-signed, SMTP clients
need to skip certificate verification (as `scripts/send_test_emails.py`
does) — this is intended for local/dev use; put a trusted TLS-terminating
proxy in front for production.

**Web UI** always requires HTTP Basic Auth on every route, including the
static UI itself. Set both `SMTPWEB_WEB_USERNAME` and
`SMTPWEB_WEB_PASSWORD` to use your own credentials, or leave both unset
and the server generates a random password on first run, writing it to
`<data_dir>/../web_credentials.json` (reused on restart). Basic Auth over
plain HTTP still sends credentials base64-encoded, not encrypted — put a
TLS-terminating reverse proxy in front before exposing this beyond
localhost/a trusted network.

Setting only one of a pair of username/password env vars (for either
service) is treated as a misconfiguration and the process refuses to
start.

## Docker

Each container runs one process from the same image, selected by
overriding the command:

```bash
docker build -t smtpweb .
docker run -d --name smtpweb-smtp -p 1025:1025 -v "$(pwd)/data:/data" \
  smtpweb python -m smtpweb.smtp_main
docker run -d --name smtpweb-web -p 8080:8080 -v "$(pwd)/data:/data" \
  smtpweb python -m smtpweb.web_main
```

Or with Docker Compose, which brings both up together as one stack, each
in its own container, sharing `./data`:

```bash
docker compose up -d --build
```

Emails and credential/cert files are stored under `/data` inside each
container (`SMTPWEB_DATA_DIR=/data/emails`); the compose file bind-mounts
`./data` so you can inspect them on the host while the containers run.

For a real deployment, only the `smtp` service needs to be reachable from
the public internet — keep the `web` service on an internal network or
behind a VPN/proxy, since it's the one with no built-in TLS.

## Storage layout

```
<data_dir>/../smtp_credentials.json   # SMTP AUTH credentials, if auto-generated
<data_dir>/../web_credentials.json    # web UI Basic Auth credentials, if auto-generated
<data_dir>/../tls/cert.pem, key.pem   # self-signed cert used for SMTP STARTTLS
<data_dir>/<email-id>/
  raw.eml              # the full original message
  metadata.json         # parsed headers, recipients, attachment index
  body.txt               # text/plain part, if present
  body.html              # text/html part, if present
  attachments/<filename>
```

## API

All routes below require HTTP Basic Auth (see [Authentication](#authentication)).

- `GET /api/emails` — list received emails (metadata only)
- `GET /api/emails/{id}` — full detail, including body text/html
- `GET /api/emails/{id}/raw` — download the original `.eml`
- `GET /api/emails/{id}/attachments/{filename}` — download an attachment
