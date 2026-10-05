#!/usr/bin/env bash
# Nightly Postgres dump. Add to cron:  0 2 * * * /srv/madresa-library/deploy/backup.sh
set -euo pipefail
BACKUP_DIR=${BACKUP_DIR:-/srv/madresa-library/backups}
mkdir -p "$BACKUP_DIR"
STAMP=$(date +%Y-%m-%d)
# DATABASE_URL is read from .env
set -a; source /srv/madresa-library/.env; set +a
pg_dump "$DATABASE_URL" | gzip > "$BACKUP_DIR/library-$STAMP.sql.gz"
# keep 30 days
find "$BACKUP_DIR" -name 'library-*.sql.gz' -mtime +30 -delete
# optional: aws s3 cp "$BACKUP_DIR/library-$STAMP.sql.gz" s3://your-bucket/library-backups/
