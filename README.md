# smtpweb

An SMTP server that accepts incoming email, sorts it into one mailbox per
recipient address on the filesystem, plus a web UI for each recipient to
log in and browse their own mail and attachments.

- SMTP handling: [`aiosmtpd`](https://aiosmtpd.readthedocs.io/)
- Web backend: [FastAPI](https://fastapi.tiangolo.com/) + [Uvicorn](https://www.uvicorn.org/)
- Frontend: static HTML/CSS/vanilla JS served by FastAPI

## Architecture

SMTP receipt and the web UI are two independent processes — `smtpweb.smtp_main`
and `smtpweb.web_main` — that share nothing but received mail on disk.
There's no in-memory state or IPC between them: the SMTP process writes
each message straight into `SMTPWEB_MAIL_DIR`, and the web process reads
that same directory on every API request. Each has its own separate
authentication and its own credential storage (see below), so a
compromise of one doesn't hand over the other's secrets.

In Docker they run as two separate containers with **separate volume
mounts**, not just separate processes: the `smtp` container can read/write
mail and its own SMTP AUTH credentials/TLS key, but has no access at all
to the web login credentials; the `web` container can read/write web login
credentials, but only has **read-only** access to mail, and no access at
all to the SMTP credentials/TLS key. This means you can expose the `smtp`
container publicly while keeping `web` off the public network entirely,
and a bug in either process can't be used to read or tamper with the
other's secrets.

## Setup

Requires Python 3.10+.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
# or: pip install -r requirements.txt
```

## Testing

```bash
pip install -e ".[test]"
# or: pip install -r requirements-test.txt
pytest
```

Or in Docker, against the actual packaged (non-editable) install — the
`test` build stage isn't part of the default build target, so it never
ends up in the production image:

```bash
docker build --target test -t smtpweb:test .
docker run --rm smtpweb:test
```

The suite (`tests/`) is unit/integration-level and doesn't touch the real
`./data` directory — every test uses a fresh `tmp_path`. Coverage
includes mailbox address sanitization/path-traversal, password hashing
and the atomic first-login claim (including a concurrency test for the
claim race), SMTP AUTH and credential auto-generation, storage
read/write and mailbox isolation, and the full web API via FastAPI's
`TestClient` (login/logout, session scoping, cross-mailbox access
blocked).

## Running

Run each process (in separate terminals):

```bash
python -m smtpweb.smtp_main
python -m smtpweb.web_main
```

This starts:

- an SMTP server on `0.0.0.0:1025`
- a web UI on `http://0.0.0.0:8080`

On first run, since no SMTP credentials are configured, `smtp_main`
generates a random SMTP username/password — see
[Authentication](#authentication) below. Send some test emails (the
script authenticates automatically using those generated credentials):

```bash
python scripts/send_test_emails.py
```

This delivers mail to `bob@example.com` and `eve@example.com`. Open
`http://127.0.0.1:8080` and log in as `bob@example.com` with any password
you like — since that mailbox has never been logged into before, that
password is now set as `bob@example.com`'s password, and you'll see his
mail. Logging in as `eve@example.com` the same way gives you a separate
account that only sees mail addressed to her.

## Configuration

All settings are read from environment variables:

| Variable                    | Default        | Description                                    |
|------------------------------|----------------|--------------------------------------------------|
| `SMTPWEB_SMTP_HOST`         | `0.0.0.0`      | SMTP listen address                             |
| `SMTPWEB_SMTP_PORT`         | `1025`         | SMTP listen port                                |
| `SMTPWEB_SMTP_USERNAME`     | *(generated)*  | SMTP AUTH username                              |
| `SMTPWEB_SMTP_PASSWORD`     | *(generated)*  | SMTP AUTH password                              |
| `SMTPWEB_WEB_HOST`          | `0.0.0.0`      | Web UI listen address                           |
| `SMTPWEB_WEB_PORT`          | `8080`         | Web UI listen port                              |
| `SMTPWEB_MAIL_DIR`          | `./data/mail`  | Received mail, one subdirectory per mailbox     |
| `SMTPWEB_SMTP_STATE_DIR`    | `./data/smtp`  | SMTP AUTH credentials + TLS cert (smtp_main only) |
| `SMTPWEB_WEB_STATE_DIR`     | `./data/web`   | Per-mailbox web login credentials (web_main only) |

Binding to the standard SMTP port 25 requires root privileges; the default
port 1025 avoids that for local development.

## Authentication

There are two independent, unrelated auth systems here — logging into the
SMTP server (to send mail in) is nothing to do with logging into a mailbox
in the web UI (to read mail out). Neither has an open/anonymous mode.

**SMTP** always requires `AUTH`, over `STARTTLS` only, with a single
service-wide credential (not per-mailbox) that controls who can relay mail
into the server at all. On startup it presents a self-signed TLS
certificate, auto-generated on first run and cached at
`SMTPWEB_SMTP_STATE_DIR/tls/` (reused on restart). Set both
`SMTPWEB_SMTP_USERNAME` and `SMTPWEB_SMTP_PASSWORD` to use your own
credentials, or leave both unset and the server generates a random
password on first run.

Like the web mailbox passwords below, it's never stored in plaintext or
reversibly encrypted — only a PBKDF2-HMAC-SHA256 hash + random salt is
written to `SMTPWEB_SMTP_STATE_DIR/smtp_credentials.json` (reused on
restart, see `src/smtpweb/password_hashing.py`). That means the plaintext
is only ever shown once, at the moment it's generated (in the startup
log, or printed by the script below) — capture it then, since it can't be
read back from that file afterward. To rotate it and print the new
plaintext password for pasting into another system's config:

```bash
python scripts/reset_smtp_password.py
```

This only writes the new credentials file — restart `smtp_main` (or the
`smtp` container) afterward for it to take effect. Since the certificate
is self-signed, SMTP clients also need to skip certificate verification
(as `scripts/send_test_emails.py` does) — this is intended for local/dev
use; put a trusted TLS-terminating proxy in front for production.

**Web UI** logins are per-mailbox: the username is the recipient email
address, and there's no separate signup step. The first time anyone logs
in for a given address, whatever password they submit becomes that
mailbox's password (self-service claiming); every login after that must
match it. Passwords are never stored in plaintext or reversibly encrypted
— each is a PBKDF2-HMAC-SHA256 hash with its own random salt
(`hashlib.pbkdf2_hmac`, 310,000 iterations), written to
`SMTPWEB_WEB_STATE_DIR/<mailbox>/credentials.json` and verified with a
constant-time comparison (see `src/smtpweb/mailbox_auth.py`). A logged-in
session (an HttpOnly cookie, held in-memory server-side) can only see mail
in its own mailbox.

Because claiming a mailbox requires nothing but knowing the address, this
is only appropriate for a server that isn't exposed to the internet —
anyone who knows/guesses an address could claim it first. **This is not
implemented, but the fix would be:** verify the person actually controls
that address before letting them claim it or reset its password — e.g.
generate a one-time code, email it to that address using the SMTP side of
this same app, and require it back before setting a new password. See the
docstring on `MailboxAuth` in `src/smtpweb/mailbox_auth.py` for where this
would go.

Setting only one of a pair of `SMTPWEB_SMTP_USERNAME`/`SMTPWEB_SMTP_PASSWORD`
is treated as a misconfiguration and `smtp_main` refuses to start.

## Docker

Each container runs one process from the same image, selected by
overriding the command, with separate volume mounts per container so
neither can read the other's credentials:

```bash
docker build -t smtpweb .

docker run -d --name smtpweb-smtp -p 1025:1025 \
  -v "$(pwd)/data/mail:/data/mail" \
  -v "$(pwd)/data/smtp:/data/smtp" \
  smtpweb python -m smtpweb.smtp_main

docker run -d --name smtpweb-web -p 8080:8080 \
  -v "$(pwd)/data/mail:/data/mail:ro" \
  -v "$(pwd)/data/web:/data/web" \
  smtpweb python -m smtpweb.web_main
```

Or with Docker Compose, which brings both up together as one stack, each
in its own container with the mounts above already wired up:

```bash
docker compose up -d --build
```

You can inspect mail, SMTP credentials, and web login credentials on the
host at `./data/mail`, `./data/smtp`, and `./data/web` respectively while
the containers run — but note the `web` container itself only ever has
read-only access to `./data/mail`, and no access at all to `./data/smtp`.

For a real deployment, only the `smtp` container needs to be reachable
from the public internet — keep the `web` container on an internal
network or behind a VPN/proxy, since (a) it has no built-in TLS and (b)
its self-service mailbox claiming has no ownership verification (see
[Authentication](#authentication)).

## Storage layout

```
data/mail/<mailbox>/emails/<email-id>/
  raw.eml              # the full original message
  metadata.json         # parsed headers, recipients, attachment index
  body.txt               # text/plain part, if present
  body.html              # text/html part, if present
  attachments/<filename>
  attachments/thumbnails/<filename>.png   # PDF attachments only, first page

data/smtp/smtp_credentials.json   # SMTP AUTH username + PBKDF2 hash + salt
data/smtp/tls/cert.pem, key.pem   # self-signed cert used for SMTP STARTTLS

data/web/<mailbox>/credentials.json   # that mailbox's web login (PBKDF2 hash + salt)
```

A message addressed to multiple recipients is stored as a full copy under
each recipient's mailbox (each gets its own `metadata.json`, but they
share the same `<email-id>`).

## API

All routes below except `/api/login` require a logged-in session (see
[Authentication](#authentication)) and are scoped to that session's
mailbox — there's no way to pass a different mailbox in in the request.

- `POST /api/login` — `{"username": "<email>", "password": "..."}`; claims the mailbox on first use
- `POST /api/logout`
- `GET /api/me` — the logged-in mailbox address
- `GET /api/emails` — list received emails (metadata only)
- `GET /api/emails/{id}` — full detail, including body text/html
- `GET /api/emails/{id}/raw` — download the original `.eml`
- `GET /api/emails/{id}/attachments/{filename}` — fetch an attachment; PDFs, common image types, and plain text render inline in the browser (e.g. printer-scanned PDFs preview directly), everything else downloads. The inline/download decision is made server-side from the filename extension, never from the sender-claimed content type, so a mislabeled attachment can't render inline — see `INLINE_SAFE_MEDIA_TYPES` in `src/smtpweb/web/app.py`.
- `GET /api/emails/{id}/attachments/{filename}/thumbnail` — a PNG of a PDF attachment's first page (rendered with `pypdfium2` when the message is received), used by the UI to show a thumbnail without downloading the whole PDF; 404 if the attachment isn't a PDF or the PDF couldn't be rendered.

In the web UI, image and PDF-with-thumbnail attachments render inline as thumbnails; clicking one opens it in a popup (an `<img>` for images, the browser's native PDF viewer in an `<iframe>` for PDFs) with an X to close, rather than downloading. A separate download icon on each thumbnail (visible on hover) downloads the file directly regardless.
