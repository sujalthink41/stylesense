#!/bin/sh
# Runs inside the backup container: one compressed pg_dump a night, old ones pruned.
set -eu

dump() {
  file="/backups/stylesense-$(date +%Y%m%d-%H%M).sql.gz"
  if pg_dump --no-owner --no-privileges | gzip > "$file.tmp"; then
    mv "$file.tmp" "$file"
    echo "backup ok: $file ($(du -h "$file" | cut -f1))"
  else
    rm -f "$file.tmp"
    echo "backup FAILED" >&2
  fi
  find /backups -name 'stylesense-*.sql.gz' -mtime +"$KEEP_DAYS" -delete
}

[ "${1:-}" = "now" ] && { dump; exit 0; }

while true; do
  now=$(date +%s)
  next=$(date -d "$(date +%Y-%m-%d) 02:30" +%s 2>/dev/null || echo $((now + 86400)))
  [ "$next" -le "$now" ] && next=$((next + 86400))
  sleep $((next - now))
  dump
done
