#!/bin/sh
set -eu
umask 077
case "${BACKUP_RETENTION_DAYS:-}" in
  ''|*[!0-9]*) exit 2 ;;
esac
test "$BACKUP_RETENTION_DAYS" -ge 1
test -n "$BACKUP_AGE_RECIPIENT"
while :; do
  if test -f /db-backup-status/last-success.txt; then
    stamp=$(tr -d ':\n-' < /db-backup-status/last-success.txt)
    case "$stamp" in
      ''|*[!0-9TZ]*) exit 2 ;;
    esac
    previous=$(cat /backups/last-success.txt 2>/dev/null || true)
    if test "$stamp" != "$previous"; then
      output="/backups/files-$stamp.zip.age"
      if test -f "$output" || python -m ops.backup_assets "$output" --recipient "$BACKUP_AGE_RECIPIENT"; then
        date -u +%FT%TZ > /backups/last-completed-at.txt
        printf '%s\n' "$stamp" > /backups/last-success.txt
        find /backups -maxdepth 1 -type f -name 'files-*.zip.age' -mtime "+$BACKUP_RETENTION_DAYS" -delete
      else
        echo 'Asset backup failed; last-success unchanged' >&2
      fi
    fi
  fi
  sleep 60
done
