#!/bin/sh
set -eu

# Bind-mounted /data often arrives root-owned; fix ownership then drop privileges.
mkdir -p /data/actual
if [ "$(id -u)" = "0" ]; then
  chown -R app:app /data
  exec setpriv --reuid="$(id -u app)" --regid="$(id -g app)" --init-groups -- "$@"
fi

exec "$@"
