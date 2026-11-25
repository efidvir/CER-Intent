#!/bin/sh
# Copy the reference data the image carries into /app/data when a fresh volume is mounted there
# (files already in the volume are kept), then run the command.
set -eu
seed=/app/data.seed
data=/app/data
if [ -d "$seed" ]; then
  mkdir -p "$data" 2>/dev/null || true
  for f in "$seed"/* "$seed"/.[!.]*; do
    [ -e "$f" ] || continue
    name=$(basename "$f")
    [ -e "$data/$name" ] || cp -R "$f" "$data/$name" 2>/dev/null || echo "entrypoint: could not copy $name into $data" >&2
  done
fi
if ! ( : > "$data/.write-test" ) 2>/dev/null; then
  echo "entrypoint: $data is not writable by uid $(id -u); intents and audit records cannot be kept" >&2
else
  rm -f "$data/.write-test"
fi
exec "$@"
