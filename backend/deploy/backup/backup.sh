#!/bin/sh
set -eu
umask 077
case "${BACKUP_RETENTION_DAYS:-}:${BACKUP_INTERVAL_SECONDS:-}" in
  *[!0-9:]*|:*|*:) exit 2 ;;
  *) : ;;
esac
test "$BACKUP_RETENTION_DAYS" -ge 1
test "$BACKUP_INTERVAL_SECONDS" -ge 60
test -n "$BACKUP_AGE_RECIPIENT"
mkdir -p /backups
while :; do
  stamp=$(date -u +%Y%m%dT%H%M%SZ)
  if pg_dump --format=custom --file=/tmp/seal.dump && age -r "$BACKUP_AGE_RECIPIENT" -o "/backups/seal-$stamp.dump.age.tmp" /tmp/seal.dump; then
    mv "/backups/seal-$stamp.dump.age.tmp" "/backups/seal-$stamp.dump.age"
    (cd /backups && sha256sum "seal-$stamp.dump.age" > "seal-$stamp.dump.age.sha256")
    date -u +%FT%TZ > /backups/last-success.txt
    if test -d /status; then
      cp /backups/last-success.txt /status/last-success.txt
      chmod 644 /status/last-success.txt
    fi
    find /backups -maxdepth 1 -type f -name 'seal-*.dump.age*' -mtime "+$BACKUP_RETENTION_DAYS" -delete
  else
    echo 'Backup failed; last-success unchanged' >&2
  fi
  rm -f /tmp/seal.dump
  sleep "$BACKUP_INTERVAL_SECONDS"
done
