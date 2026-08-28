#!/bin/sh
set -e

# A bind-mounted host directory that doesn't exist yet gets created by the
# Docker daemon itself (as root), the first time it sees the mount --
# regardless of what user the image says it runs as. So the image baking
# in `chown smtpweb /data` at build time only helps named volumes (which
# initialize their content, ownership included, from the image); a fresh
# bind mount still shows up here owned by someone other than smtpweb.
# Fix it up at runtime instead, once per boot, before dropping to the
# unprivileged user -- this is why this stage starts as root at all.
for dir in /data/mail /data/smtp /data/web; do
    if [ -d "$dir" ] && [ "$(stat -c %u "$dir")" != "$(id -u smtpweb)" ]; then
        chown -R smtpweb:smtpweb "$dir"
    fi
done

# exec (not a plain call) so gosu's own exec into the target command
# replaces this shell as PID 1 -- signals like SIGTERM from `docker
# stop` reach the actual python process directly, which is what
# smtp/main.py's and web/main.py's own signal handlers expect.
exec gosu smtpweb "$@"
